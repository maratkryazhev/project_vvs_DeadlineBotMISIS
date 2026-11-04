"""Серверная часть Web GUI (API) на aiohttp."""

import asyncio
import logging
from datetime import datetime
from typing import Optional
from aiohttp import web

from database import AsyncDatabase
from bot.bot_service import BotRunner

logger = logging.getLogger("WebGUI")

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <title>Дедлайны группы</title>
</head>
<body>
    <h1>Сервер API успешно запущен!</h1>
    <p>Проверка API: <a href="/api/student_dashboard?user_id=1">/api/student_dashboard</a></p>
</body>
</html>
"""

class WebDashboardApp:
    def __init__(self, db_path: str, token: str, host: str = "127.0.0.1", port: int = 8080):
        self.db_path = db_path
        self.token = token
        self.host = host
        self.port = port
        self.db = AsyncDatabase(db_path)
        self.bot_runner: Optional[BotRunner] = None
        self.bot_task: Optional[asyncio.Task] = None
        self.app = web.Application()
        self._setup_routes()

    def log(self, message: str):
        now_str = datetime.now().strftime("%H:%M:%S")
        logger.info(f"[{now_str}] {message}")

    def _setup_routes(self):
        """Настройка маршрутов (URL), по которым сайт будет стучаться к серверу."""
        self.app.router.add_get("/", self.handle_index)
        self.app.router.add_get("/api/student_dashboard", self.handle_student_dashboard)
        self.app.router.add_post("/api/deadlines", self.handle_add_deadline)
        self.app.router.add_delete("/api/deadlines", self.handle_delete_deadline)
        self.app.router.add_post("/api/toggle_done", self.handle_toggle_done)
        self.app.router.add_post("/api/join_group", self.handle_join_group)
        self.app.router.add_get("/api/groups", self.handle_get_groups)

    async def handle_index(self, request):
        """Отдает главную HTML-страницу."""
        return web.Response(text=HTML_TEMPLATE, content_type="text/html")

    async def handle_student_dashboard(self, request):
        """Отдает данные о студенте, его группе и дедлайнах в формате JSON."""
        user_id_param = request.query.get("user_id")
        user_id = int(user_id_param) if user_id_param and user_id_param.isdigit() else None

        user = None
        group = None
        group_id = None

        if user_id:
            user = await self.db.get_or_create_user(user_id)
            if user.get("group_id"):
                group_id = user["group_id"]
                group = await self.db.get_group_by_id(group_id)

        # Если user_id не передан, берем первую группу из базы (для теста)
        if not group:
            groups = await self.db.get_all_groups()
            if groups:
                group = groups[0]
                group_id = group["id"]

        deadlines = []
        members = []
        if group_id:
            raw_deadlines = await self.db.get_group_deadlines(group_id, user_id=user_id)
            for d in raw_deadlines:
                item = dict(d)
                item["remaining"] = "Считается на клиенте"
                deadlines.append(item)
            members = await self.db.get_group_members(group_id)

        return web.json_response({
            "user": user,
            "group": group,
            "deadlines": deadlines,
            "members": members
        })

    async def handle_add_deadline(self, request):
        """Принимает данные от формы и добавляет дедлайн в базу."""
        data = await request.json()
        user_id = data.get("user_id")
        group_id = data.get("group_id")
        author_name = "Студент (Web)"

        if user_id:
            user_id = int(user_id)
            user = await self.db.get_or_create_user(user_id)
            group_id = user.get("group_id") or group_id
            author_name = user.get("full_name") or user.get("username") or "Студент"

        if not group_id:
            return web.json_response({"error": "Сначала создайте группу"}, status=400)

        await self.db.add_deadline(
            group_id=group_id,
            subject=data["subject"],
            title=data["title"],
            description="Добавлено через Web API",
            due_date=data["due_date"],
            created_by_id=user_id or 0,
            created_by_name=data.get("author_name") or author_name
        )
        self.log(f"Добавлен дедлайн '{data['title']}' через Web API")
        return web.json_response({"status": "ok"})

    async def handle_toggle_done(self, request):
        """Ставит/убирает галочку 'Я сдал'."""
        data = await request.json()
        user_id = data.get("user_id")
        deadline_id = int(data["deadline_id"])

        if user_id:
            user_id = int(user_id)
            is_done = await self.db.toggle_completion(user_id, deadline_id)
            return web.json_response({"status": "ok", "completed": is_done})
        return web.json_response({"status": "ok", "completed": False})

    async def handle_join_group(self, request):
        """Позволяет студенту вступить в группу по коду."""
        data = await request.json()
        user_id = data.get("user_id")
        join_code = data.get("join_code", "").strip().upper()

        group = await self.db.get_group_by_code(join_code)
        if not group:
            return web.json_response({"error": "Группа не найдена"}, status=404)

        if user_id:
            user_id = int(user_id)
            await self.db.set_user_group(user_id, group["id"])

        return web.json_response({"status": "ok", "group": group})

    async def handle_delete_deadline(self, request):
        """Удаляет дедлайн по ID."""
        deadline_id = int(request.query.get("id"))
        await self.db.delete_deadline(deadline_id)
        self.log(f"Удален дедлайн ID {deadline_id} через Web API")
        return web.json_response({"status": "ok"})

    async def handle_get_groups(self, request):
        """Отдает список всех групп (для отладки)."""
        groups = await self.db.get_all_groups()
        return web.json_response(groups)

    async def run(self):
        """Запускает веб-сервер и бота."""
        await self.db.init_db()
        self.log("Инициализация Web GUI (API)...")

        # Автоматически стартуем бота в фоне
        if self.token:
            self.bot_runner = BotRunner(
                token=self.token,
                db_path=self.db_path,
                log_callback=self.log
            )
            self.bot_task = asyncio.create_task(self.bot_runner.run())

        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, self.host, self.port)
        await site.start()

        self.log(f"🚀 Сервер API доступен: http://{self.host}:{self.port}")

        while True:
            await asyncio.sleep(3600)