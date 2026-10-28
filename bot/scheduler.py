"""Асинхронный фоновый планировщик напоминаний."""
import asyncio
import logging
from datetime import datetime
from aiogram import Bot
from database import AsyncDatabase

logger = logging.getLogger("Scheduler")


def format_remaining_time(due_date_str: str) -> str:
    """Форматирует оставшееся время до дедлайна в человекочитаемый вид."""
    try:
        due = datetime.strptime(due_date_str, "%Y-%m-%d %H:%M:%S")
        now = datetime.now()
        diff = due - now

        if diff.total_seconds() <= 0:
            return "⏰ Время истекло!"

        days = diff.days
        hours = diff.seconds // 3600
        minutes = (diff.seconds % 3600) // 60

        parts = []
        if days > 0: parts.append(f"{days} дн.")
        if hours > 0: parts.append(f"{hours} ч.")
        if minutes > 0 and days == 0: parts.append(f"{minutes} мин.")

        return " ".join(parts) if parts else "Менее 1 мин."
    except Exception:
        return due_date_str


async def reminder_worker(bot: Bot, db: AsyncDatabase, interval_seconds: int = 30, log_callback=None):
    def log(msg: str):
        logger.info(msg)
        if log_callback:
            try:
                log_callback(f"[Напоминания] {msg}")
            except Exception:
                pass

    log(f"Планировщик запущен (интервал: {interval_seconds} сек.)")

    while True:
        try:
            upcoming = await db.get_deadlines_for_24h_reminder()
            for item in upcoming:
                members = await db.get_group_members(item["group_id"])
                reminded_count = 0
                for member in members:
                    user_id = member["telegram_id"]
                    if await db.is_completed(user_id, item["id"]):
                        continue

                    text = (
                        f"🚨 <b>Внимание! Дедлайн через 24 часа!</b>\n\n"
                        f"📚 <b>Предмет:</b> {item['subject']}\n"
                        f"📝 <b>Задание:</b> {item['title']}\n"
                        f"⏰ <b>Срок:</b> <code>{item['due_date']}</code>\n"
                    )
                    try:
                        await bot.send_message(chat_id=user_id, text=text, parse_mode="HTML")
                        reminded_count += 1
                        await asyncio.sleep(0.05)  # Защита от лимитов Telegram
                    except Exception as e:
                        logger.warning(f"Не отправлено {user_id}: {e}")

                await db.mark_reminder_sent(item["id"])
                log(f"Отправлено {reminded_count} напоминаний по '{item['title']}'")

        except asyncio.CancelledError:
            log("Планировщик остановлен.")
            break
        except Exception as e:
            logger.error(f"Ошибка планировщика: {e}")

        await asyncio.sleep(interval_seconds)