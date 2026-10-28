from __future__ import annotations
import re
from datetime import datetime
from typing import Union
from aiogram import Router, F
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.types import Message, CallbackQuery, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from bot.scheduler import format_remaining_time

from database import AsyncDatabase
from bot.keyboards import (
    main_menu_keyboard,
    deadline_action_keyboard,
    cancel_keyboard,
    skip_or_cancel_keyboard
)

router = Router()


class AddDeadlineFSM(StatesGroup):
    waiting_for_subject = State()
    waiting_for_title = State()
    waiting_for_description = State()
    waiting_for_due_date = State()


class JoinGroupFSM(StatesGroup):
    waiting_for_code = State()


class CreateGroupFSM(StatesGroup):
    waiting_for_name = State()
    waiting_for_code = State()


def parse_datetime(input_text: str) -> str:
    """Парсит различные форматы даты и времени и возвращает строку в формате ISO: YYYY-MM-DD HH:MM:SS

    Поддерживает форматы:
    - 25.12.2026 18:00
    - 25.12.2026 18:00:00
    - 25.12.2026 (устанавливает 23:59:00)
    - 25.12 18:00 (берет текущий год)
    - 2026-12-25 18:00
    """
    text = input_text.strip()
    now = datetime.now()

    patterns = [
        ("%d.%m.%Y %H:%M", False),
        ("%d.%m.%Y %H:%M:%S", False),
        ("%Y-%m-%d %H:%M", False),
        ("%Y-%m-%d %H:%M:%S", False),
        ("%d.%m.%Y", True),  # если без времени - конец дня
        ("%d.%m %H:%M", False),
        ("%d.%m", True),
    ]

    for pattern, is_date_only in patterns:
        try:
            parsed = datetime.strptime(text, pattern)
            # Если в шаблоне нет года (например, %d.%m), подставляем текущий
            if "%Y" not in pattern:
                parsed = parsed.replace(year=now.year)
            if is_date_only:
                parsed = parsed.replace(hour=23, minute=59, second=0)
            return parsed.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue

    raise ValueError("Неверный формат даты")


# =====================================================================
# СТАРТ И ОБЩИЕ КОМАНДЫ
# =====================================================================

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, db: AsyncDatabase):
    await state.clear()
    user_id = message.from_user.id
    username = message.from_user.username or ""
    full_name = message.from_user.full_name or ""

    user = await db.get_or_create_user(user_id, username, full_name)

    welcome_text = (
        f"👋 Привет, <b>{full_name}</b>!\n\n"
        f"Я бот для совместного отслеживания дедлайнов учебной группы.\n"
    )

    if user.get("group_id"):
        group = await db.get_group_by_id(user["group_id"])
        group_name = group["name"] if group else "Неизвестно"
        code = group["join_code"] if group else "-"
        welcome_text += (
            f"🎓 <b>Твоя группа:</b> {group_name} (Код: <code>{code}</code>)\n\n"
            f"Выбирай действие в меню ниже или вводи команды."
        )
    else:
        welcome_text += (
            "⚠️ Ты пока <b>не состоишь ни в одной группе</b>.\n\n"
            "Чтобы видеть дедлайны и получать напоминания:\n"
            "• Присоединись по коду группы: /join\n"
            "• Или создай новую группу для одногруппников: /create_group"
        )

    await message.answer(welcome_text, parse_mode="HTML", reply_markup=main_menu_keyboard(user_id=user_id))


@router.message(Command("help"))
@router.callback_query(F.data == "show_help")
async def show_help(event: Union[Message, CallbackQuery]):
    help_text = (
        "📖 <b>Справочник команд бота:</b>\n\n"
        "📅 <b>Дедлайны:</b>\n"
        "• /deadlines — показать все активные дедлайны группы\n"
        "• /add — добавить новый дедлайн (доступно любому студенту)\n\n"
        "👥 <b>Управление группой:</b>\n"
        "• /group — информация о текущей группе и код приглашения\n"
        "• /join — войти в существующую группу по коду\n"
        "• /create_group — создать новую группу\n\n"
        "🔔 <b>Авто-напоминания:</b>\n"
        "Бот автоматически присылает уведомление ровно <b>за 24 часа</b> до сдачи "
        "всем студентам группы, которые еще не нажали кнопку <i>«Я сдал»</i>."
    )
    if isinstance(event, CallbackQuery):
        await event.answer()
        await event.message.answer(help_text, parse_mode="HTML")
    else:
        await event.answer(help_text, parse_mode="HTML")


@router.message(Command("cancel"))
@router.message(F.text.casefold() == "❌ отмена")
async def cmd_cancel(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        await message.answer("Нет активного действия для отмены.", reply_markup=ReplyKeyboardRemove())
        return

    await state.clear()
    await message.answer(
        "Действие отменено.",
        reply_markup=ReplyKeyboardRemove()
    )
    await message.answer("Главное меню:", reply_markup=main_menu_keyboard(user_id=message.from_user.id))


# =====================================================================
# СПИСОК ДЕДЛАЙНОВ И ОТМЕТКА «Я СДАЛ»
# =====================================================================

@router.message(Command("deadlines"))
@router.callback_query(F.data == "show_deadlines")
async def list_deadlines(event: Union[Message, CallbackQuery], db: AsyncDatabase):
    user_id = event.from_user.id
    user = await db.get_or_create_user(user_id)

    if not user.get("group_id"):
        text = "⚠️ Ты еще не присоединился к группе! Введи /join <код> или /create_group."
        if isinstance(event, CallbackQuery):
            await event.answer()
            await event.message.answer(text)
        else:
            await event.answer(text)
        return

    group = await db.get_group_by_id(user["group_id"])
    group_name = group["name"] if group else "Группа"

    deadlines = await db.get_group_deadlines(user["group_id"], user_id=user_id)

    if isinstance(event, CallbackQuery):
        await event.answer()

    target_message = event.message if isinstance(event, CallbackQuery) else event

    if not deadlines:
        await target_message.answer(
            f"🎉 В группе <b>{group_name}</b> пока нет дедлайнов!\n"
            f"Ты можешь добавить первый с помощью команды /add.",
            parse_mode="HTML",
            reply_markup=main_menu_keyboard(user_id=user_id)
        )
        return

    await target_message.answer(
        f"📋 <b>Дедлайны группы {group_name}:</b>\n<i>(Нажми кнопку «Я сдал», чтобы отметить выполнение)</i>",
        parse_mode="HTML"
    )

    for d in deadlines:
        is_done = bool(d["is_completed"])
        status_icon = "✅" if is_done else "⏳"
        status_line = "<b>Статус:</b> СДАНО ✅" if is_done else f"<b>Осталось:</b> {format_remaining_time(d['due_date'])}"

        author = d.get("created_by_name") or "Студент"
        card_text = (
            f"{status_icon} <b>{d['subject']}</b> — <i>{d['title']}</i>\n"
            f"⏰ <b>Дедлайн:</b> <code>{d['due_date']}</code>\n"
            f"⌛ {status_line}\n"
        )
        if d.get("description"):
            card_text += f"💬 <b>Инфо:</b> {d['description']}\n"
        card_text += f"👤 <i>Добавил(а): {author}</i>"

        can_delete = (d["created_by_id"] == user_id)
        kb = deadline_action_keyboard(d["id"], is_done, can_delete=can_delete)
        await target_message.answer(card_text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data.startswith("toggle_done:"))
async def on_toggle_done(callback: CallbackQuery, db: AsyncDatabase):
    deadline_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id

    now_done = await db.toggle_completion(user_id, deadline_id)
    deadline = await db.get_deadline_by_id(deadline_id)

    if not deadline:
        await callback.answer("Дедлайн не найден или уже удален.", show_alert=True)
        return

    status_str = "отмечен как СДАННЫЙ! Молодец 🎉" if now_done else "отметка о сдаче снята 🔄"
    await callback.answer(f"Дедлайн {status_str}")

    # Обновляем клавиатуру на сообщении
    can_delete = (deadline["created_by_id"] == user_id)
    await callback.message.edit_reply_markup(
        reply_markup=deadline_action_keyboard(deadline_id, now_done, can_delete=can_delete)
    )


@router.callback_query(F.data.startswith("delete_deadline:"))
async def on_delete_deadline(callback: CallbackQuery, db: AsyncDatabase):
    deadline_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id

    deadline = await db.get_deadline_by_id(deadline_id)
    if not deadline:
        await callback.answer("Дедлайн уже удален.", show_alert=True)
        return

    # Удалить может автор или любой студент при обоюдном согласии
    if deadline["created_by_id"] != user_id:
        await callback.answer("Удалить дедлайн может только его создатель!", show_alert=True)
        return

    await db.delete_deadline(deadline_id)
    await callback.answer("Дедлайн успешно удален.")
    await callback.message.edit_text(
        f"🗑 <s>{callback.message.text}</s>\n\n<i>(Дедлайн удален автором)</i>",
        parse_mode="HTML"
    )


# =====================================================================
# ДОБАВЛЕНИЕ ДЕДЛАЙНА (FSM КОНЕЧНЫЙ АВТОМАТ)
# =====================================================================

@router.message(Command("add"))
@router.callback_query(F.data == "add_deadline_start")
async def start_add_deadline(event: Union[Message, CallbackQuery], state: FSMContext, db: AsyncDatabase):
    user_id = event.from_user.id
    user = await db.get_or_create_user(user_id)

    if not user.get("group_id"):
        text = "⚠️ Сначала присоединись к группе: /join <код> или /create_group."
        if isinstance(event, CallbackQuery):
            await event.answer()
            await event.message.answer(text)
        else:
            await event.answer(text)
        return

    if isinstance(event, CallbackQuery):
        await event.answer()
        target = event.message
    else:
        target = event

    await state.set_state(AddDeadlineFSM.waiting_for_subject)
    await target.answer(
        "📝 <b>Шаг 1 из 4:</b> Введи название предмета (дисциплины):\n"
        "<i>Например: Математический анализ, Введение в специальность, Программирование</i>",
        parse_mode="HTML",
        reply_markup=cancel_keyboard()
    )


@router.message(AddDeadlineFSM.waiting_for_subject)
async def process_subject(message: Message, state: FSMContext):
    subject = message.text.strip()
    if len(subject) < 2:
        await message.answer("Слишком короткое название предмета. Попробуй еще раз:")
        return

    await state.update_data(subject=subject)
    await state.set_state(AddDeadlineFSM.waiting_for_title)
    await message.answer(
        f"Предмет: <b>{subject}</b>\n\n"
        "📝 <b>Шаг 2 из 4:</b> Что именно нужно сдать? (Название работы):\n"
        "<i>Например: Лабораторная №3, Реферат, Домашка к семинару</i>",
        parse_mode="HTML",
        reply_markup=cancel_keyboard()
    )


@router.message(AddDeadlineFSM.waiting_for_title)
async def process_title(message: Message, state: FSMContext):
    title = message.text.strip()
    if len(title) < 2:
        await message.answer("Слишком короткое название задания. Попробуй еще раз:")
        return

    await state.update_data(title=title)
    await state.set_state(AddDeadlineFSM.waiting_for_description)
    await message.answer(
        f"Задание: <b>{title}</b>\n\n"
        "📝 <b>Шаг 3 из 4:</b> Дополнительное описание или ссылки (необязательно):\n"
        "<i>Например: вариант 4, отправить на почту преподу, критерии в беседе</i>",
        parse_mode="HTML",
        reply_markup=skip_or_cancel_keyboard()
    )


@router.message(AddDeadlineFSM.waiting_for_description)
async def process_description(message: Message, state: FSMContext):
    desc = ""
    if message.text.strip() != "⏩ Пропустить описание":
        desc = message.text.strip()

    await state.update_data(description=desc)
    await state.set_state(AddDeadlineFSM.waiting_for_due_date)
    await message.answer(
        "⏰ <b>Шаг 4 из 4:</b> Укажи срок сдачи (дедлайн):\n\n"
        "Примеры правильного формата:\n"
        "• <code>25.12.2026 18:00</code>\n"
        "• <code>25.12.2026</code> <i>(автоматически установит 23:59)</i>\n"
        "• <code>25.12 18:00</code> <i>(текущий год)</i>",
        parse_mode="HTML",
        reply_markup=cancel_keyboard()
    )


@router.message(AddDeadlineFSM.waiting_for_due_date)
async def process_due_date(message: Message, state: FSMContext, db: AsyncDatabase):
    try:
        iso_date = parse_datetime(message.text)
    except ValueError:
        await message.answer(
            "⚠️ Не удалось распознать дату. Пожалуйста, используй формат:\n"
            "<code>ДД.ММ.ГГГГ ЧЧ:ММ</code> (например: <code>30.11.2026 23:59</code>)",
            parse_mode="HTML"
        )
        return

    data = await state.get_data()
    user_id = message.from_user.id
    user = await db.get_or_create_user(user_id)
    group_id = user["group_id"]
    author_name = message.from_user.full_name or message.from_user.username or "Студент"

    deadline_id = await db.add_deadline(
        group_id=group_id,
        subject=data["subject"],
        title=data["title"],
        description=data.get("description", ""),
        due_date=iso_date,
        created_by_id=user_id,
        created_by_name=author_name
    )

    await state.clear()
    await message.answer("✅ Дедлайн успешно добавлен в группу!", reply_markup=ReplyKeyboardRemove())

    card = (
        f"📌 <b>Новый дедлайн добавлен:</b>\n"
        f"📚 <b>Предмет:</b> {data['subject']}\n"
        f"📝 <b>Задание:</b> {data['title']}\n"
        f"⏰ <b>Срок сдачи:</b> <code>{iso_date}</code>\n"
        f"⏳ <b>Осталось:</b> {format_remaining_time(iso_date)}\n"
    )
    if data.get("description"):
        card += f"💬 <b>Инфо:</b> {data['description']}\n"
    card += f"👤 <i>Добавил(а): {author_name}</i>"

    kb = deadline_action_keyboard(deadline_id, is_completed=False, can_delete=True)
    await message.answer(card, parse_mode="HTML", reply_markup=kb)
    await message.answer("Главное меню:", reply_markup=main_menu_keyboard(user_id=message.from_user.id))


# =====================================================================
# УПРАВЛЕНИЕ ГРУППОЙ (СОЗДАНИЕ / ВХОД / ИНФО)
# =====================================================================

@router.message(Command("group"))
@router.callback_query(F.data == "show_group_info")
async def show_group(event: Union[Message, CallbackQuery], db: AsyncDatabase):
    user_id = event.from_user.id
    user = await db.get_or_create_user(user_id)

    target = event.message if isinstance(event, CallbackQuery) else event
    if isinstance(event, CallbackQuery):
        await event.answer()

    if not user.get("group_id"):
        await target.answer(
            "⚠️ Ты не состоишь в группе. Воспользуйся /join <код> или /create_group.",
            reply_markup=main_menu_keyboard(user_id=user_id)
        )
        return

    group = await db.get_group_by_id(user["group_id"])
    members = await db.get_group_members(user["group_id"])

    text = (
        f"🎓 <b>Информация о группе:</b>\n\n"
        f"👥 <b>Название:</b> {group['name']}\n"
        f"🔑 <b>Код для входа:</b> <code>{group['join_code']}</code>\n"
        f"👨‍🎓 <b>Количество участников:</b> {len(members)}\n\n"
        f"<i>Отправь одногруппникам код <code>{group['join_code']}</code>, чтобы они присоединились через команду /join {group['join_code']}</i>"
    )
    await target.answer(text, parse_mode="HTML", reply_markup=main_menu_keyboard(user_id=user_id))


@router.message(Command("join"))
@router.callback_query(F.data == "change_group")
async def cmd_join(event: Union[Message, CallbackQuery], state: FSMContext, db: AsyncDatabase):
    if isinstance(event, CallbackQuery):
        await event.answer()
        target = event.message
    else:
        target = event

    # Если передали аргумент: /join IVT21
    if isinstance(event, Message):
        parts = event.text.split(maxsplit=1)
        if len(parts) > 1:
            code = parts[1].strip().upper()
            await apply_join_group(event, code, db)
            return

    await state.set_state(JoinGroupFSM.waiting_for_code)
    await target.answer(
        "🔑 Введи <b>код группы</b> для присоединения (спроси у старосты или одногруппника):",
        parse_mode="HTML",
        reply_markup=cancel_keyboard()
    )


@router.message(JoinGroupFSM.waiting_for_code)
async def process_join_code(message: Message, state: FSMContext, db: AsyncDatabase):
    code = message.text.strip().upper()
    await state.clear()
    await apply_join_group(message, code, db)


async def apply_join_group(message: Message, code: str, db: AsyncDatabase):
    group = await db.get_group_by_code(code)
    if not group:
        await message.answer(
            f"❌ Группа с кодом <code>{code}</code> не найдена.\n"
            f"Проверь правильность кода или создай новую группу: /create_group",
            parse_mode="HTML",
            reply_markup=ReplyKeyboardRemove()
        )
        await message.answer("Главное меню:", reply_markup=main_menu_keyboard(user_id=message.from_user.id))
        return

    user_id = message.from_user.id
    await db.set_user_group(user_id, group["id"])

    await message.answer(
        f"🎉 Ты успешно присоединился к группе <b>{group['name']}</b>!\n"
        f"Теперь ты можешь смотреть дедлайны по команде /deadlines.",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardRemove()
    )
    await message.answer("Главное меню:", reply_markup=main_menu_keyboard(user_id=message.from_user.id))


@router.message(Command("create_group"))
async def cmd_create_group(message: Message, state: FSMContext):
    await state.set_state(CreateGroupFSM.waiting_for_name)
    await message.answer(
        "🏷 Введи <b>название новой группы</b> (например, <i>БПМ-26-6-3</i>):",
        parse_mode="HTML",
        reply_markup=cancel_keyboard()
    )


@router.message(CreateGroupFSM.waiting_for_name)
async def process_create_group_name(message: Message, state: FSMContext):
    name = message.text.strip()
    if len(name) < 2:
        await message.answer("Название слишком короткое. Попробуй еще раз:")
        return

    # Предложим код на основе названия
    cleaned_code = re.sub(r"[^A-Za-z0-9А-Яа-я]", "", name).upper()[:8]
    await state.update_data(name=name)
    await state.set_state(CreateGroupFSM.waiting_for_code)

    await message.answer(
        f"Название: <b>{name}</b>\n\n"
        f"🔑 Теперь придумай короткий <b>код приглашения</b> (например, <code>{cleaned_code}</code>):\n"
        f"По этому коду твои одногруппники смогут подключиться.",
        parse_mode="HTML",
        reply_markup=cancel_keyboard()
    )


@router.message(CreateGroupFSM.waiting_for_code)
async def process_create_group_code(message: Message, state: FSMContext, db: AsyncDatabase):
    code = message.text.strip().upper()
    data = await state.get_data()
    name = data["name"]

    group_id = await db.create_group(name=name, join_code=code)
    await state.clear()

    if not group_id:
        await message.answer(
            f"❌ Группа с кодом <code>{code}</code> уже существует. Пожалуйста, придумай другой код.",
            parse_mode="HTML",
            reply_markup=ReplyKeyboardRemove()
        )
        return

    # Автоматически привязываем создателя к созданной группе
    await db.set_user_group(message.from_user.id, group_id)

    await message.answer(
        f"🎓 Группа <b>{name}</b> успешно создана!\n"
        f"🔑 Код приглашения: <code>{code}</code>\n\n"
        f"Ты уже добавлен в нее. Отправь код друзьям, чтобы они тоже присоединились!",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardRemove()
    )
    await message.answer("Главное меню:", reply_markup=main_menu_keyboard(user_id=message.from_user.id))