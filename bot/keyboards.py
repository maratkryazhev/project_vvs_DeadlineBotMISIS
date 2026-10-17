from typing import Optional
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, WebAppInfo
import config


def main_menu_keyboard(web_app_url: Optional[str] = None, user_id: Optional[int] = None) -> InlineKeyboardMarkup:
    """Главное меню бота с поддержкой персонального Telegram Mini App."""
    url = (web_app_url or config.WEB_APP_URL or "").strip()
    buttons = []

    # Добавляем user_id в URL для мгновенной персонализации под конкретного студента
    if url.startswith("https://"):
        personal_url = f"{url}?user_id={user_id}" if user_id else url
        buttons.append([
            InlineKeyboardButton(
                text="📱 Открыть дедлайны моей группы",
                web_app=WebAppInfo(url=personal_url)
            )
        ])
    elif url.startswith("http://"):
        personal_url = f"{url}?user_id={user_id}" if user_id else url
        buttons.append([
            InlineKeyboardButton(
                text="🌐 Открыть панель в браузере",
                url=personal_url
            )
        ])

    buttons.extend([
        [
            InlineKeyboardButton(text="📅 Мои дедлайны", callback_data="show_deadlines"),
            InlineKeyboardButton(text="➕ Добавить дедлайн", callback_data="add_deadline_start")
        ],
        [
            InlineKeyboardButton(text="👥 Моя группа", callback_data="show_group_info"),
            InlineKeyboardButton(text="🔄 Сменить группу", callback_data="change_group")
        ],
        [
            InlineKeyboardButton(text="ℹ️ Справка и команды", callback_data="show_help")
        ]
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def deadline_action_keyboard(deadline_id: int, is_completed: bool, can_delete: bool = False) -> InlineKeyboardMarkup:
    """Клавиатура под отдельным дедлайном."""
    status_text = "❌ Отменить сдачу" if is_completed else "✅ Я сдал!"
    status_cb = f"toggle_done:{deadline_id}"

    buttons = [
        [InlineKeyboardButton(text=status_text, callback_data=status_cb)]
    ]
    if can_delete:
        buttons.append([
            InlineKeyboardButton(text="🗑 Удалить дедлайн", callback_data=f"delete_deadline:{deadline_id}")
        ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def cancel_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура для отмены ввода FSM."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Отмена")]],
        resize_keyboard=True,
        one_time_keyboard=True
    )


def skip_or_cancel_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура для пропуска необязательного шага."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="⏩ Пропустить описание")],
            [KeyboardButton(text="❌ Отмена")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )