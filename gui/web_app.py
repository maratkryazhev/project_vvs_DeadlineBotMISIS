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
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>🎓 Дедлайны группы</title>
    <!-- Telegram Web App SDK -->
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
    <style>
        :root {
            --bg-color: var(--tg-theme-bg-color, #0f172a);
            --card-bg: var(--tg-theme-secondary-bg-color, #1e293b);
            --border-color: #334155;
            --primary: var(--tg-theme-button-color, #3b82f6);
            --primary-text: var(--tg-theme-button-text-color, #ffffff);
            --success: #10b981;
            --danger: #ef4444;
            --warning: #f59e0b;
            --text-main: var(--tg-theme-text-color, #f8fafc);
            --text-muted: var(--tg-theme-hint-color, #94a3b8);
        }
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
        body { background: var(--bg-color); color: var(--text-main); padding: 12px; min-height: 100vh; }
        .container { max-width: 600px; margin: 0 auto; }

        /* Карточка профиля и группы */
        .group-header-card { background: linear-gradient(135deg, rgba(59, 130, 246, 0.15), rgba(30, 41, 59, 0.7)); border: 1px solid rgba(59, 130, 246, 0.3); border-radius: 14px; padding: 14px; margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center; }
        .group-name-title { font-size: 18px; font-weight: 700; color: #60a5fa; display: flex; align-items: center; gap: 6px; }
        .group-subtitle { font-size: 12px; color: var(--text-muted); margin-top: 2px; }
        .copy-code-btn { background: rgba(59, 130, 246, 0.2); color: #93c5fd; border: 1px solid rgba(59, 130, 246, 0.4); border-radius: 8px; padding: 6px 12px; font-size: 12px; font-weight: 600; cursor: pointer; }

        /* Вкладки */
        .tabs { display: flex; gap: 6px; margin-bottom: 12px; background: rgba(0,0,0,0.25); padding: 4px; border-radius: 10px; }
        .tab-btn { flex: 1; background: transparent; border: none; color: var(--text-muted); padding: 9px; border-radius: 8px; font-size: 13px; font-weight: 600; cursor: pointer; text-align: center; transition: 0.15s; }
        .tab-btn.active { background: var(--primary); color: var(--primary-text); }

        .tab-content { display: none; }
        .tab-content.active { display: block; }

        /* Карточки дедлайнов */
        .deadline-card { background: var(--card-bg); border: 1px solid var(--border-color); border-radius: 12px; padding: 14px; margin-bottom: 10px; display: flex; flex-direction: column; gap: 8px; }
        .deadline-card.completed { opacity: 0.65; border-color: rgba(16, 185, 129, 0.4); }

        .card-top { display: flex; justify-content: space-between; align-items: flex-start; gap: 8px; }
        .subject-badge { font-size: 13px; font-weight: 700; color: #60a5fa; text-transform: uppercase; letter-spacing: 0.5px; }
        .deadline-title { font-size: 16px; font-weight: 600; margin-top: 2px; color: var(--text-main); }
        .card-top.completed .deadline-title { text-decoration: line-through; }

        .badge { display: inline-flex; align-items: center; gap: 4px; padding: 4px 8px; border-radius: 6px; font-size: 11px; font-weight: 600; }
        .badge-warning { background: rgba(245, 158, 11, 0.2); color: #fbbf24; }
        .badge-success { background: rgba(16, 185, 129, 0.2); color: #34d399; }

        .card-bottom { display: flex; justify-content: space-between; align-items: center; font-size: 12px; color: var(--text-muted); padding-top: 8px; border-top: 1px solid rgba(255,255,255,0.06); }

        .actions-row { display: flex; align-items: center; gap: 8px; }
        .btn-check { display: inline-flex; align-items: center; gap: 6px; background: rgba(255,255,255,0.05); border: 1px solid var(--border-color); color: var(--text-main); border-radius: 8px; padding: 6px 12px; font-size: 12px; font-weight: 600; cursor: pointer; }
        .btn-check.checked { background: rgba(16, 185, 129, 0.2); border-color: var(--success); color: #34d399; }
        .btn-del { background: transparent; border: none; color: #ef4444; font-size: 14px; cursor: pointer; padding: 4px; }

        /* Формы */
        .form-card { background: var(--card-bg); border: 1px solid var(--border-color); border-radius: 12px; padding: 16px; }
        .form-group { display: flex; flex-direction: column; gap: 6px; margin-bottom: 12px; }
        .form-group label { font-size: 12px; color: var(--text-muted); font-weight: 500; }
        input { background: #0b1120; border: 1px solid var(--border-color); border-radius: 8px; padding: 11px; color: var(--text-main); font-size: 14px; outline: none; width: 100%; }
        input:focus { border-color: var(--primary); }

        button.btn-submit { width: 100%; background: var(--primary); color: var(--primary-text); border: none; border-radius: 8px; padding: 12px; font-weight: 600; font-size: 14px; cursor: pointer; margin-top: 6px; }
        .btn-quick { background: rgba(255, 255, 255, 0.08); border: 1px solid var(--border-color); color: var(--text-muted); border-radius: 6px; padding: 5px 10px; font-size: 11px; font-weight: 600; cursor: pointer; transition: 0.15s; }
        .btn-quick:active { background: var(--primary); color: #fff; }

        .empty-state { text-align: center; padding: 32px 16px; color: var(--text-muted); font-size: 14px; line-height: 1.6; }
    </style>
</head>
<body>
    <div class="container">
        <!-- Шапка: Название группы текущего студента -->
        <div class="group-header-card">
            <div>
                <div class="group-name-title">
                    🎓 <span id="headerGroupName">Загрузка группы...</span>
                </div>
                <div class="group-subtitle" id="headerStudentGreeting">Загрузка профиля...</div>
            </div>
            <button class="copy-code-btn" id="btnCopyCode" onclick="copyJoinCode()">
                🔑 Код: <span id="headerGroupCode">...</span> 📋
            </button>
        </div>

        <!-- Переключатель вкладок -->
        <div class="tabs">
            <button class="tab-btn active" onclick="switchTab('tabDeadlines', this)">📋 Дедлайны (<span id="tabCount">0</span>)</button>
            <button class="tab-btn" onclick="switchTab('tabAdd', this)">➕ Добавить</button>
            <button class="tab-btn" onclick="switchTab('tabGroup', this)">👥 Одногруппники</button>
        </div>

        <!-- ВКЛАДКА 1: ДЕДЛАЙНЫ ТОЛЬКО МОЕЙ ГРУППЫ -->
        <div id="tabDeadlines" class="tab-content active">
            <div id="deadlinesContainer"></div>
        </div>

        <!-- ВКЛАДКА 2: ДОБАВЛЕНИЕ (АВТОМАТИЧЕСКИ В СВОЮ ГРУППУ) -->
        <div id="tabAdd" class="tab-content">
            <div class="form-card">
                <div style="font-size:15px; font-weight:600; margin-bottom:12px;">➕ Добавить дедлайн для <span id="addGroupTargetName" style="color:#60a5fa;">группы</span></div>

                <div class="form-group">
                    <label>Предмет / Дисциплина:</label>
                    <input type="text" id="addSubject" placeholder="Например: Высшая математика, Физика">
                </div>
                <div class="form-group">
                    <label>Название задания:</label>
                    <input type="text" id="addTitle" placeholder="Например: Лабораторная работа №3">
                </div>
                <div class="form-group">
                    <label>📅 Срок сдачи (выберите дату и время):</label>
                    <input type="datetime-local" id="addDueDate" style="color-scheme: dark;">
                    <div style="display:flex; gap:6px; margin-top:6px;">
                        <button type="button" class="btn-quick" onclick="setQuickDate(1)">+1 день</button>
                        <button type="button" class="btn-quick" onclick="setQuickDate(3)">+3 дня</button>
                        <button type="button" class="btn-quick" onclick="setQuickDate(7)">+1 неделя</button>
                        <button type="button" class="btn-quick" onclick="setQuickDate(14)">+2 недели</button>
                    </div>
                </div>
                <button class="btn-submit" onclick="submitDeadline()">🚀 Опубликовать для всей группы</button>
            </div>
        </div>

        <!-- ВКЛАДКА 3: ОДНОГРУППНИКИ И СМЕНА ГРУППЫ -->
        <div id="tabGroup" class="tab-content">
            <div class="form-card" style="margin-bottom:12px;">
                <div style="font-size:15px; font-weight:600; margin-bottom:10px;">👥 Одногруппники в боте (<span id="membersCount">0</span> чел.)</div>
                <div id="membersList" style="font-size:13px; color:var(--text-muted); line-height:1.8;"></div>
            </div>

            <div class="form-card">
                <div style="font-size:15px; font-weight:600; margin-bottom:10px;">🔄 Присоединиться к другой группе</div>
                <div class="form-group">
                    <label>Код новой группы:</label>
                    <input type="text" id="newGroupCode" placeholder="Например: 1122 или IVT21">
                </div>
                <button class="btn-submit" style="background:#475569;" onclick="joinNewGroup()">Войти по коду</button>
            </div>
        </div>
    </div>

    <script>
        // Определяем Telegram Web App контекст
        const tg = window.Telegram?.WebApp;
        if (tg) {
            tg.ready();
            tg.expand();
        }

        // Получаем user_id из URL (?user_id=123) или из Telegram initData
        const urlParams = new URLSearchParams(window.location.search);
        let currentUserId = urlParams.get('user_id');
        if (!currentUserId && tg?.initDataUnsafe?.user?.id) {
            currentUserId = tg.initDataUnsafe.user.id;
        }

        let studentGroupCode = "";

        function switchTab(tabId, btn) {
            document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
            document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
            document.getElementById(tabId).classList.add('active');
            btn.classList.add('active');
        }

        async function loadStudentDashboard() {
            try {
                const url = currentUserId ? `/api/student_dashboard?user_id=${currentUserId}` : '/api/student_dashboard';
                const res = await fetch(url);
                const data = await res.json();

                // Данные студента и группы
                document.getElementById('headerGroupName').textContent = data.group ? data.group.name : "Нет группы";
                document.getElementById('headerGroupCode').textContent = data.group ? data.group.join_code : "—";
                studentGroupCode = data.group ? data.group.join_code : "";

                // Извлекаем реальное имя пользователя Telegram
                let studentName = "";
                if (tg?.initDataUnsafe?.user) {
                    const u = tg.initDataUnsafe.user;
                    if (u.first_name) {
                        studentName = u.last_name ? `${u.first_name} ${u.last_name}` : u.first_name;
                    } else if (u.username) {
                        studentName = `@${u.username}`;
                    }
                }
                if (!studentName && data.user) {
                    studentName = data.user.full_name || (data.user.username ? `@${data.user.username}` : "");
                }
                if (!studentName) {
                    studentName = "студент";
                }
                window.currentStudentName = studentName;
                document.getElementById('headerStudentGreeting').textContent = `Привет, ${studentName}! 👋`;
                document.getElementById('addGroupTargetName').textContent = data.group ? data.group.name : "своей группы";

                // Дедлайны группы
                const deadlines = data.deadlines || [];
                document.getElementById('tabCount').textContent = deadlines.length;
                renderDeadlines(deadlines);

                // Одногруппники
                const members = data.members || [];
                document.getElementById('membersCount').textContent = members.length;
                const membersDiv = document.getElementById('membersList');
                if (members.length === 0) {
                    membersDiv.innerHTML = "Ты пока первый в группе!";
                } else {
                    membersDiv.innerHTML = members.map((m, i) => `${i + 1}. ${m.full_name || m.username || 'Студент'}`).join('<br>');
                }
            } catch (e) {
                console.error(e);
            }
        }

        function renderDeadlines(deadlines) {
            const container = document.getElementById('deadlinesContainer');
            container.innerHTML = '';

            if (deadlines.length === 0) {
                container.innerHTML = `
                    <div class="empty-state">
                        🎉 <b>В твоей группе пока нет дедлайнов!</b><br>
                        Нажми вкладку <b>«➕ Добавить»</b> выше, чтобы внести первое задание для одногруппников.
                    </div>
                `;
                return;
            }

            deadlines.forEach(d => {
                const card = document.createElement('div');
                const isDone = Boolean(d.is_completed);
                card.className = `deadline-card ${isDone ? 'completed' : ''}`;

                card.innerHTML = `
                    <div class="card-top ${isDone ? 'completed' : ''}">
                        <div>
                            <div class="subject-badge">${d.subject}</div>
                            <div class="deadline-title">${d.title}</div>
                        </div>
                        <span class="badge ${isDone ? 'badge-success' : 'badge-warning'}">
                            ${isDone ? '✅ Сдано' : '⏳ ' + d.remaining}
                        </span>
                    </div>
                    <div class="card-bottom">
                        <div>⏰ <code>${d.due_date}</code></div>
                        <div class="actions-row">
                            <button class="btn-check ${isDone ? 'checked' : ''}" onclick="toggleDone(${d.id})">
                                ${isDone ? '✅ Я сдал' : '⬜️ Отметить'}
                            </button>
                            <button class="btn-del" title="Удалить дедлайн" onclick="deleteDeadline(${d.id})">🗑</button>
                        </div>
                    </div>
                `;
                container.appendChild(card);
            });
        }

        async function toggleDone(deadlineId) {
            await fetch('/api/toggle_done', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user_id: currentUserId, deadline_id: deadlineId })
            });
            loadStudentDashboard();
        }

        async function deleteDeadline(deadlineId) {
            if (!confirm('Удалить этот дедлайн для всей группы?')) return;
            await fetch(`/api/deadlines?id=${deadlineId}`, { method: 'DELETE' });
            loadStudentDashboard();
        }

        async function submitDeadline() {
            const subject = document.getElementById('addSubject').value.trim();
            const title = document.getElementById('addTitle').value.trim();
            const rawDate = document.getElementById('addDueDate').value.trim();

            if (!subject || !title || !rawDate) {
                alert('Пожалуйста, заполни предмет, задание и выбери дату!');
                return;
            }

            // Преобразуем формат "2026-12-01T23:59" в "2026-12-01 23:59:00"
            let due_date = rawDate.replace('T', ' ');
            if (due_date.length === 16) {
                due_date += ':00';
            }

            await fetch('/api/deadlines', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    user_id: currentUserId,
                    subject,
                    title,
                    due_date,
                    author_name: window.currentStudentName || ""
                })
            });

            document.getElementById('addSubject').value = '';
            document.getElementById('addTitle').value = '';

            // Переключаем на список дедлайнов
            document.querySelectorAll('.tab-btn')[0].click();
            loadStudentDashboard();
        }

        function setQuickDate(daysAhead) {
            const now = new Date();
            now.setDate(now.getDate() + daysAhead);
            const yyyy = now.getFullYear();
            const mm = String(now.getMonth() + 1).padStart(2, '0');
            const dd = String(now.getDate()).padStart(2, '0');
            document.getElementById('addDueDate').value = `${yyyy}-${mm}-${dd}T23:59`;
        }

        async function joinNewGroup() {
            const code = document.getElementById('newGroupCode').value.trim().toUpperCase();
            if (!code) {
                alert('Введи код группы!');
                return;
            }

            const res = await fetch('/api/join_group', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user_id: currentUserId, join_code: code })
            });

            if (!res.ok) {
                alert('Группа с таким кодом не найдена!');
                return;
            }

            document.getElementById('newGroupCode').value = '';
            alert('Ты успешно переключился в новую группу!');
            document.querySelectorAll('.tab-btn')[0].click();
            loadStudentDashboard();
        }

        function copyJoinCode() {
            if (!studentGroupCode) return;
            navigator.clipboard.writeText(studentGroupCode);
            alert(`Код группы ${studentGroupCode} скопирован в буфер! Отправь его одногруппникам.`);
        }

        // Устанавливаем дату по умолчанию (+7 дней)
        setQuickDate(7);

        loadStudentDashboard();
        setInterval(loadStudentDashboard, 5000);
    </script>
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