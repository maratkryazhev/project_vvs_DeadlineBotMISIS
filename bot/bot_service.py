"""Сервис управления жизненным циклом Telegram-бота в asyncio."""

import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from database import AsyncDatabase
from bot.handlers import router as bot_router

logger = logging.getLogger("BotService")


class BotRunner:
    """Управляет асинхронным запуском и остановкой Telegram-бота."""

    def __init__(self, token: str, db_path: str, log_callback=None):
        self.token = token
        self.db_path = db_path
        self.log_callback = log_callback
        self.bot: Bot = None
        self.dp: Dispatcher = None
        self.db: AsyncDatabase = None
        self.scheduler_task: asyncio.Task = None
        self.is_running = False

    def log(self, message: str):
        logger.info(message)
        if self.log_callback:
            try:
                self.log_callback(message)
            except Exception:
                pass

    async def run(self):
        """Запускает опрос (polling) и планировщик в цикле asyncio."""
        try:
            self.bot = Bot(token=self.token)
            self.dp = Dispatcher(storage=MemoryStorage())
            self.db = AsyncDatabase(self.db_path)

            # Инициализируем таблицы БД асинхронно
            await self.db.init_db()

            # Регистрируем БД в контексте обработчиков aiogram
            self.dp["db"] = self.db
            bot_router._parent_router = None
            self.dp.include_router(bot_router)

            # Получаем информацию о боте для проверки токена
            me = await self.bot.get_me()
            self.is_running = True
            self.log(f"🟢 Бот успешно подключен как @{me.username} ({me.first_name})")

            self.log("🚀 Запущен асинхронный Polling сообщений Telegram...")
            # Сбрасываем старые накопившиеся апдейты и начинаем опрос
            await self.bot.delete_webhook(drop_pending_updates=True)
            await self.dp.start_polling(self.bot)

        except asyncio.CancelledError:
            self.log("Остановка бота по запросу пользователя...")
        except Exception as e:
            self.log(f"❌ Ошибка в работе бота: {e}")
            raise
        finally:
            await self.shutdown()

    async def shutdown(self):
        """Корректно останавливает все асинхронные задачи."""
        self.is_running = False
        if self.bot:
            try:
                await self.bot.session.close()
            except Exception:
                pass

        self.log("🔴 Бот остановлен.")