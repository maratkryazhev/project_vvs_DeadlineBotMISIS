"""Графический интерфейс панели управления ботом и учета дедлайнов на Tkinter & ttk (тема Clam).

Кроссплатформенный интерфейс: стабильно работает на всех версиях macOS, Windows и Linux.
Не зависит от багов Carbon/Aqua в старых версиях Tkinter.
"""

import os
os.environ["TK_SILENCE_DEPRECATION"] = "1"

import threading
import asyncio
import datetime
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional

from database import SyncDatabase
from bot.bot_service import BotRunner
from bot.scheduler import format_remaining_time


class DeadlineManagerGUI:
    def __init__(self, db_path: str, default_token: str = ""):
        self.db_path = db_path
        self.sync_db = SyncDatabase(db_path)
        self.bot_token = default_token

        # Потоки и асинхронный цикл бота
        self.bot_thread: Optional[threading.Thread] = None
        self.bot_loop: Optional[asyncio.AbstractEventLoop] = None
        self.bot_runner: Optional[BotRunner] = None
        self.group_map = {}

        # Создание главного окна
        self.root = tk.Tk()
        self.root.title("🎓 Университетский трекер дедлайнов & Telegram-бот")
        self.root.geometry("980x680")
        self.root.minsize(820, 540)
        self.root.configure(bg="#f4f6f9")

        # Настройка стабильной темы Clam со своим стилем
        self._setup_styles()

        self._build_ui()
        self.refresh_all_data()

    def _setup_styles(self):
        self.style = ttk.Style(self.root)
        if "clam" in self.style.theme_names():
            self.style.theme_use("clam")

        bg_main = "#f4f6f9"
        fg_text = "#2c3e50"
        accent_blue = "#3498db"
        card_bg = "#ffffff"

        # Базовые стили
        self.style.configure(".", background=bg_main, foreground=fg_text, font=("Helvetica", 11))
        self.style.configure("TFrame", background=bg_main)

        # Рамки блоков (LabelFrame)
        self.style.configure(
            "TLabelframe",
            background=bg_main,
            bordercolor="#dcdde1",
            relief="solid",
            borderwidth=1
        )
        self.style.configure(
            "TLabelframe.Label",
            background=bg_main,
            foreground="#2980b9",
            font=("Helvetica", 11, "bold")
        )

        # Карточки статистики
        self.style.configure(
            "Card.TLabelframe",
            background=card_bg,
            bordercolor="#e2e8f0",
            relief="solid",
            borderwidth=1
        )
        self.style.configure(
            "Card.TLabelframe.Label",
            background=card_bg,
            foreground="#7f8c8d",
            font=("Helvetica", 10)
        )

        # Кнопки
        self.style.configure(
            "TButton",
            background="#ffffff",
            foreground="#2c3e50",
            bordercolor="#cbd5e1",
            font=("Helvetica", 10, "bold"),
            padding=(8, 4)
        )
        self.style.map(
            "TButton",
            background=[("active", "#e2e8f0"), ("disabled", "#f1f5f9")],
            foreground=[("disabled", "#94a3b8")]
        )

        self.style.configure(
            "Primary.TButton",
            background="#27ae60",
            foreground="#ffffff",
            font=("Helvetica", 10, "bold"),
            padding=(10, 5)
        )
        self.style.map(
            "Primary.TButton",
            background=[("active", "#219653"), ("disabled", "#95a5a6")]
        )

        self.style.configure(
            "Danger.TButton",
            background="#e74c3c",
            foreground="#ffffff",
            font=("Helvetica", 10, "bold"),
            padding=(10, 5)
        )
        self.style.map(
            "Danger.TButton",
            background=[("active", "#c0392b"), ("disabled", "#95a5a6")]
        )

        # Вкладки (Notebook)
        self.style.configure("TNotebook", background=bg_main, borderwidth=0)
        self.style.configure(
            "TNotebook.Tab",
            background="#e2e8f0",
            foreground="#475569",
            padding=(12, 6),
            font=("Helvetica", 10, "bold")
        )
        self.style.map(
            "TNotebook.Tab",
            background=[("selected", "#ffffff")],
            foreground=[("selected", "#1e293b")]
        )

        # Таблицы (Treeview)
        self.style.configure(
            "Treeview",
            background="#ffffff",
            foreground="#1e293b",
            fieldbackground="#ffffff",
            rowheight=26,
            font=("Helvetica", 10)
        )
        self.style.configure(
            "Treeview.Heading",
            background="#e2e8f0",
            foreground="#1e293b",
            font=("Helvetica", 10, "bold")
        )
        self.style.map(
            "Treeview",
            background=[("selected", "#3498db")],
            foreground=[("selected", "#ffffff")]
        )

    def _build_ui(self):
        # 1. Верхняя панель управления ботом
        self._build_top_panel()

        # 2. Карточки статистики
        self._build_stats_panel()

        # 3. Вкладки (Дедлайны, Группы, Логи)
        self._build_notebook()

    def _build_top_panel(self):
        top_frame = ttk.LabelFrame(self.root, text=" Управление Telegram-ботом ", padding=10)
        top_frame.pack(fill="x", padx=15, pady=(10, 6))

        # Левая часть: статус
        status_frame = ttk.Frame(top_frame)
        status_frame.pack(side="left", fill="y", padx=5)

        ttk.Label(status_frame, text="Статус бота:").pack(side="left", padx=(0, 6))
        self.status_lbl = tk.Label(
            status_frame,
            text="🔴 Остановлен",
            fg="#c0392b",
            bg="#f4f6f9",
            font=("Helvetica", 11, "bold")
        )
        self.status_lbl.pack(side="left")

        # Правая часть: кнопка запуска, остановки и токен
        ctrl_frame = ttk.Frame(top_frame)
        ctrl_frame.pack(side="right", fill="y", padx=5)

        ttk.Label(ctrl_frame, text="Токен:").pack(side="left", padx=(0, 4))
        self.token_entry = ttk.Entry(ctrl_frame, width=28)
        self.token_entry.pack(side="left", padx=(0, 10))
        if self.bot_token:
            self.token_entry.insert(0, self.bot_token)

        self.btn_start = ttk.Button(
            ctrl_frame,
            text="▶️ Запустить бота",
            style="Primary.TButton",
            command=self.start_bot
        )
        self.btn_start.pack(side="left", padx=4)

        self.btn_stop = ttk.Button(
            ctrl_frame,
            text="⏹ Остановить бота",
            style="Danger.TButton",
            state="disabled",
            command=self.stop_bot
        )
        self.btn_stop.pack(side="left", padx=4)

    def _build_stats_panel(self):
        stats_frame = ttk.Frame(self.root, padding=(15, 2))
        stats_frame.pack(fill="x")

        self.stat_groups_val = self._create_stat_box(stats_frame, "👥 Групп в базе", "0")
        self.stat_users_val = self._create_stat_box(stats_frame, "👨‍🎓 Студентов в боте", "0")
        self.stat_deadlines_val = self._create_stat_box(stats_frame, "⏰ Всего дедлайнов", "0")
        self.stat_active_val = self._create_stat_box(stats_frame, "🔥 Горящих дедлайнов", "0")

    def _create_stat_box(self, parent, title: str, val: str):
        box = ttk.LabelFrame(parent, text=f" {title} ", style="Card.TLabelframe", padding=(10, 6))
        box.pack(side="left", fill="both", expand=True, padx=4)

        val_lbl = tk.Label(box, text=val, font=("Helvetica", 16, "bold"), fg="#2980b9", bg="#ffffff")
        val_lbl.pack(pady=2)
        return val_lbl

    def _build_notebook(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=15, pady=(8, 15))

        # Создаем вкладки
        self.tab_deadlines = ttk.Frame(self.notebook, padding=10)
        self.tab_groups = ttk.Frame(self.notebook, padding=10)
        self.tab_logs = ttk.Frame(self.notebook, padding=10)

        self.notebook.add(self.tab_deadlines, text=" 📋 Дедлайны групп ")
        self.notebook.add(self.tab_groups, text=" 👥 Группы и студенты ")
        self.notebook.add(self.tab_logs, text=" 📜 Логи и события (Async) ")

        self._setup_deadlines_tab()
        self._setup_groups_tab()
        self._setup_logs_tab()

    # --- ВКЛАДКА 1: ДЕДЛАЙНЫ ---
    def _setup_deadlines_tab(self):
        toolbar = ttk.Frame(self.tab_deadlines)
        toolbar.pack(fill="x", pady=(0, 8))

        ttk.Label(toolbar, text="Фильтр по группе:").pack(side="left", padx=(0, 5))
        self.group_filter_var = tk.StringVar(value="Все группы")
        self.group_filter_combo = ttk.Combobox(
            toolbar,
            textvariable=self.group_filter_var,
            state="readonly",
            values=["Все группы"],
            width=20
        )
        self.group_filter_combo.pack(side="left", padx=5)
        self.group_filter_combo.bind("<<ComboboxSelected>>", lambda _: self.load_deadlines_table())

        btn_refresh = ttk.Button(toolbar, text="🔄 Обновить", command=self.refresh_all_data)
        btn_refresh.pack(side="right", padx=4)

        btn_del = ttk.Button(toolbar, text="🗑 Удалить дедлайн", command=self.delete_selected_deadline)
        btn_del.pack(side="right", padx=4)

        btn_add = ttk.Button(toolbar, text="➕ Добавить дедлайн", style="Primary.TButton", command=self.open_add_deadline_dialog)
        btn_add.pack(side="right", padx=4)

        # Таблица дедлайнов (Treeview)
        tree_frame = ttk.Frame(self.tab_deadlines)
        tree_frame.pack(fill="both", expand=True)

        columns = ("id", "group", "subject", "title", "due_date", "remaining", "author")
        self.deadline_tree = ttk.Treeview(tree_frame, columns=columns, show="headings", selectmode="browse")

        self.deadline_tree.heading("id", text="ID")
        self.deadline_tree.heading("group", text="Группа")
        self.deadline_tree.heading("subject", text="Предмет")
        self.deadline_tree.heading("title", text="Задание")
        self.deadline_tree.heading("due_date", text="Срок сдачи")
        self.deadline_tree.heading("remaining", text="Осталось")
        self.deadline_tree.heading("author", text="Кто добавил")

        self.deadline_tree.column("id", width=45, anchor="center")
        self.deadline_tree.column("group", width=110, anchor="center")
        self.deadline_tree.column("subject", width=160)
        self.deadline_tree.column("title", width=220)
        self.deadline_tree.column("due_date", width=140, anchor="center")
        self.deadline_tree.column("remaining", width=130, anchor="center")
        self.deadline_tree.column("author", width=130)

        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.deadline_tree.yview)
        self.deadline_tree.configure(yscrollcommand=scrollbar.set)

        self.deadline_tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

    # --- ВКЛАДКА 2: ГРУППЫ ---
    def _setup_groups_tab(self):
        toolbar = ttk.Frame(self.tab_groups)
        toolbar.pack(fill="x", pady=(0, 8))

        btn_add_group = ttk.Button(toolbar, text="➕ Создать новую группу", style="Primary.TButton", command=self.open_add_group_dialog)
        btn_add_group.pack(side="left", padx=4)

        btn_refresh = ttk.Button(toolbar, text="🔄 Обновить", command=self.refresh_all_data)
        btn_refresh.pack(side="right", padx=4)

        tree_frame = ttk.Frame(self.tab_groups)
        tree_frame.pack(fill="both", expand=True)

        columns = ("id", "name", "join_code", "members", "created_at")
        self.group_tree = ttk.Treeview(tree_frame, columns=columns, show="headings", selectmode="browse")

        self.group_tree.heading("id", text="ID")
        self.group_tree.heading("name", text="Название группы")
        self.group_tree.heading("join_code", text="Код для входа (Invite Code)")
        self.group_tree.heading("members", text="Студентов в боте")
        self.group_tree.heading("created_at", text="Дата создания")

        self.group_tree.column("id", width=50, anchor="center")
        self.group_tree.column("name", width=190)
        self.group_tree.column("join_code", width=180, anchor="center")
        self.group_tree.column("members", width=130, anchor="center")
        self.group_tree.column("created_at", width=160, anchor="center")

        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.group_tree.yview)
        self.group_tree.configure(yscrollcommand=scrollbar.set)

        self.group_tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

    # --- ВКЛАДКА 3: ЛОГИ ---
    def _setup_logs_tab(self):
        log_frame = ttk.Frame(self.tab_logs)
        log_frame.pack(fill="both", expand=True)

        self.log_text = tk.Text(
            log_frame,
            font=("Courier", 11),
            bg="#1e1e1e",
            fg="#d4d4d4",
            insertbackground="white",
            wrap="word",
            padx=10,
            pady=10
        )
        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)

        self.log_text.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        bottom_bar = ttk.Frame(self.tab_logs)
        bottom_bar.pack(fill="x", pady=(8, 0))

        btn_clear = ttk.Button(bottom_bar, text="🧹 Очистить логи", command=self.clear_logs)
        btn_clear.pack(side="right")

    # =====================================================================
    # ЛОГИРОВАНИЕ (Thread-safe)
    # =====================================================================
    def log(self, message: str):
        def _append():
            ts = datetime.datetime.now().strftime("%H:%M:%S")
            line = f"[{ts}] {message}\n"
            self.log_text.insert(tk.END, line)
            self.log_text.see(tk.END)
        self.root.after(0, _append)

    def clear_logs(self):
        self.log_text.delete("1.0", tk.END)

    # =====================================================================
    # ОБНОВЛЕНИЕ ДАННЫХ ИЗ БАЗЫ
    # =====================================================================
    def refresh_all_data(self):
        self.load_stats()
        self.load_groups_table()
        self.load_deadlines_table()

    def load_stats(self):
        stats = self.sync_db.get_stats()
        self.stat_groups_val.config(text=str(stats["groups"]))
        self.stat_users_val.config(text=str(stats["users"]))
        self.stat_deadlines_val.config(text=str(stats["deadlines"]))
        self.stat_active_val.config(text=str(stats["active_deadlines"]))

    def load_groups_table(self):
        for item in self.group_tree.get_children():
            self.group_tree.delete(item)

        groups = self.sync_db.get_all_groups()
        group_names = ["Все группы"]
        self.group_map = {}

        for g in groups:
            self.group_tree.insert(
                "", "end",
                values=(g["id"], g["name"], g["join_code"], g["member_count"], g["created_at"])
            )
            group_names.append(g["name"])
            self.group_map[g["name"]] = g["id"]

        self.group_filter_combo["values"] = group_names

    def load_deadlines_table(self):
        for item in self.deadline_tree.get_children():
            self.deadline_tree.delete(item)

        selected = self.group_filter_var.get()
        target_group_id = self.group_map.get(selected) if selected != "Все группы" else None

        deadlines = self.sync_db.get_all_deadlines(group_id=target_group_id)
        for d in deadlines:
            remaining = format_remaining_time(d["due_date"])
            self.deadline_tree.insert(
                "", "end",
                values=(
                    d["id"],
                    d.get("group_name", f"Группа {d['group_id']}"),
                    d["subject"],
                    d["title"],
                    d["due_date"],
                    remaining,
                    d.get("created_by_name") or "GUI Admin"
                )
            )

    # =====================================================================
    # ДИАЛОГИ ДОБАВЛЕНИЯ
    # =====================================================================
    def open_add_deadline_dialog(self):
        groups = self.sync_db.get_all_groups()
        if not groups:
            messagebox.showwarning("Внимание", "Сначала создайте группу во вкладке «Группы»!")
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("Добавление дедлайна")
        dialog.geometry("450x360")
        dialog.resizable(False, False)
        dialog.configure(bg="#f4f6f9")
        dialog.grab_set()

        form = ttk.Frame(dialog, padding=20)
        form.pack(fill="both", expand=True)

        ttk.Label(form, text="Группа:").grid(row=0, column=0, sticky="w", pady=5)
        group_var = tk.StringVar(value=groups[0]["name"])
        g_names = [g["name"] for g in groups]
        cb_group = ttk.Combobox(form, textvariable=group_var, values=g_names, state="readonly", width=28)
        cb_group.grid(row=0, column=1, sticky="ew", pady=5)

        ttk.Label(form, text="Предмет:").grid(row=1, column=0, sticky="w", pady=5)
        ent_subject = ttk.Entry(form, width=30)
        ent_subject.grid(row=1, column=1, sticky="ew", pady=5)

        ttk.Label(form, text="Задание:").grid(row=2, column=0, sticky="w", pady=5)
        ent_title = ttk.Entry(form, width=30)
        ent_title.grid(row=2, column=1, sticky="ew", pady=5)

        ttk.Label(form, text="Срок сдачи:").grid(row=3, column=0, sticky="w", pady=5)
        ent_due = ttk.Entry(form, width=30)
        default_due = (datetime.datetime.now() + datetime.timedelta(days=7)).strftime("%Y-%m-%d 23:59:00")
        ent_due.insert(0, default_due)
        ent_due.grid(row=3, column=1, sticky="ew", pady=5)
        ttk.Label(form, text="(Формат: ГГГГ-ММ-ДД ЧЧ:ММ:СС)", font=("Helvetica", 9), foreground="#7f8c8d").grid(row=4, column=1, sticky="w")

        def save():
            selected_g_name = group_var.get()
            group_id = next((g["id"] for g in groups if g["name"] == selected_g_name), None)
            subj = ent_subject.get().strip()
            title = ent_title.get().strip()
            due = ent_due.get().strip()

            if not subj or not title or not due:
                messagebox.showerror("Ошибка", "Заполните предмет, задание и дату!")
                return

            self.sync_db.add_deadline(
                group_id=group_id,
                subject=subj,
                title=title,
                description="Создано через GUI",
                due_date=due,
                author="Староста (GUI)"
            )
            self.log(f"Добавлен дедлайн '{title}' ({subj}) для группы {selected_g_name}")
            self.refresh_all_data()
            dialog.destroy()

        btn_save = ttk.Button(form, text="💾 Сохранить дедлайн", style="Primary.TButton", command=save)
        btn_save.grid(row=5, column=0, columnspan=2, pady=18)

    def open_add_group_dialog(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Создание группы")
        dialog.geometry("400x230")
        dialog.resizable(False, False)
        dialog.configure(bg="#f4f6f9")
        dialog.grab_set()

        form = ttk.Frame(dialog, padding=20)
        form.pack(fill="both", expand=True)

        ttk.Label(form, text="Название группы:").grid(row=0, column=0, sticky="w", pady=6)
        ent_name = ttk.Entry(form, width=24)
        ent_name.grid(row=0, column=1, sticky="ew", pady=6)

        ttk.Label(form, text="Код для входа:").grid(row=1, column=0, sticky="w", pady=6)
        ent_code = ttk.Entry(form, width=24)
        ent_code.grid(row=1, column=1, sticky="ew", pady=6)
        ttk.Label(form, text="(например: IVT21 или BPI23)", font=("Helvetica", 9), foreground="#7f8c8d").grid(row=2, column=1, sticky="w")

        def save():
            name = ent_name.get().strip()
            code = ent_code.get().strip().upper()
            if not name or not code:
                messagebox.showerror("Ошибка", "Заполните оба поля!")
                return

            res = self.sync_db.create_group(name, code)
            if not res:
                messagebox.showerror("Ошибка", "Группа с таким кодом уже существует!")
                return

            self.log(f"Создана группа '{name}' с кодом '{code}'")
            self.refresh_all_data()
            dialog.destroy()

        btn_save = ttk.Button(form, text="➕ Создать группу", style="Primary.TButton", command=save)
        btn_save.grid(row=3, column=0, columnspan=2, pady=18)

    def delete_selected_deadline(self):
        selected = self.deadline_tree.selection()
        if not selected:
            messagebox.showinfo("Инфо", "Выберите дедлайн из таблицы для удаления.")
            return

        values = self.deadline_tree.item(selected[0], "values")
        deadline_id = int(values[0])
        title = values[3]

        if messagebox.askyesno("Подтверждение", f"Удалить дедлайн '{title}' (ID {deadline_id})?"):
            self.sync_db.delete_deadline(deadline_id)
            self.log(f"Удален дедлайн ID {deadline_id} ('{title}')")
            self.refresh_all_data()

    # =====================================================================
    # УПРАВЛЕНИЕ АСИНХРОННЫМ БОТОМ (THREADING + ASYNCIO)
    # =====================================================================
    def start_bot(self):
        token = self.token_entry.get().strip()
        if not token:
            messagebox.showerror(
                "Ошибка токена",
                "Пожалуйста, укажите токен Telegram-бота!\nПолучить его можно у @BotFather."
            )
            return

        self.btn_start.config(state="disabled")
        self.token_entry.config(state="disabled")
        self.status_lbl.config(text="🟡 Запуск...", fg="#e67e22")
        self.log("Запуск бота в фоновом потоке asyncio...")

        self.bot_thread = threading.Thread(target=self._bot_thread_worker, args=(token,), daemon=True)
        self.bot_thread.start()

    def _bot_thread_worker(self, token: str):
        self.bot_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.bot_loop)

        self.bot_runner = BotRunner(
            token=token,
            db_path=self.db_path,
            log_callback=self.log
        )

        try:
            self.root.after(0, self._on_bot_started)
            self.bot_loop.run_until_complete(self.bot_runner.run())
        except Exception as e:
            self.log(f"Ошибка в работе бота: {e}")
        finally:
            self.bot_loop.close()
            self.root.after(0, self._on_bot_stopped)

    def _on_bot_started(self):
        self.status_lbl.config(text="🟢 Бот работает", fg="#27ae60")
        self.btn_start.config(state="disabled")
        self.btn_stop.config(state="normal")
        self.refresh_all_data()

    def _on_bot_stopped(self):
        self.status_lbl.config(text="🔴 Остановлен", fg="#c0392b")
        self.btn_start.config(state="normal")
        self.btn_stop.config(state="disabled")
        self.token_entry.config(state="normal")
        self.refresh_all_data()

    def stop_bot(self):
        if not self.bot_runner or not self.bot_loop:
            return

        self.log("Отправка сигнала остановки боту...")
        self.status_lbl.config(text="🟡 Остановка...", fg="#e67e22")
        self.btn_stop.config(state="disabled")

        asyncio.run_coroutine_threadsafe(self.bot_runner.shutdown(), self.bot_loop)

    def run(self):
        self.log("Графическая панель управления успешно запущена.")
        self.root.mainloop()