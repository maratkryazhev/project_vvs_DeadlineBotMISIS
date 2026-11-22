"""Главная точка входа в проект.

Запускает:
1. Асинхронный сервер Web GUI (aiohttp).
2. Автоматический фоновый HTTPS-туннель (SSH с постоянным keepalive).
3. Telegram-бота (aiogram) с привязкой кнопки Mini App.

Всё работает в едином цикле asyncio в ОДНОЙ команде!
"""

import sys
import re
import argparse
import asyncio
import webbrowser
import logging
from typing import Optional

import config
from gui.web_app import WebDashboardApp
from bot.bot_service import BotRunner

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("Main")


async def start_auto_tunnel(port: int = 8080) -> tuple[Optional[asyncio.subprocess.Process], Optional[str]]:
    """Автоматически поднимает HTTPS туннель через localhost.run в фоне с keepalive."""
    cmd = [
        "ssh",
        "-o", "StrictHostKeyChecking=no",
        "-o", "ServerAliveInterval=20",
        "-o", "ServerAliveCountMax=5",
        "-R", f"80:localhost:{port}",
        "nokey@localhost.run"
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT
        )

        tunnel_url = None
        # Читаем вывод ssh, пока не найдем https ссылку
        while True:
            line = await proc.stdout.readline()
            if not line:
                break
            text = line.decode(errors="ignore")
            match = re.search(r"https://[a-zA-Z0-9.-]+\.lhr\.life", text)
            if match:
                tunnel_url = match.group(0)
                logger.info(f"🌐 Получен рабочий HTTPS туннель: {tunnel_url}")
                break

        return proc, tunnel_url
    except Exception as e:
        logger.warning(f"Не удалось поднять автоматический туннель: {e}")
        return None, None


async def run_app():
    port = 8080
    host = "127.0.0.1"
    local_url = f"http://{host}:{port}"

    print(f"\n=======================================================")
    print(f"🎓 UNIVERSITY DEADLINE MANAGER & TELEGRAM BOT")
    print(f"🚀 Запуск локального сервера: {local_url}")
    print(f"=======================================================\n")

    # 1. Запуск Web GUI сервера
    dashboard = WebDashboardApp(
        db_path=config.DB_PATH,
        token=config.BOT_TOKEN,
        host=host,
        port=port
    )

    # 2. Поднимаем туннель в фоне, чтобы Telegram Mini App работал всегда
    tunnel_proc, tunnel_url = await start_auto_tunnel(port=port)
    active_url = tunnel_url or config.WEB_APP_URL or local_url

    if tunnel_url:
        config.WEB_APP_URL = tunnel_url
        print(f"✅ Telegram Mini App активен по адресу: {tunnel_url}")

    try:
        await dashboard.run()
    finally:
        if tunnel_proc:
            try:
                tunnel_proc.terminate()
            except Exception:
                pass


def main():
    parser = argparse.ArgumentParser(description="University Deadline Tracker & Bot")
    parser.add_argument(
        "--cli", "--no-gui",
        dest="cli",
        action="store_true",
        help="Запустить только Telegram-бота в терминале"
    )

    args = parser.parse_args()

    if args.cli:
        token = config.BOT_TOKEN
        runner = BotRunner(token=token, db_path=config.DB_PATH, log_callback=print)
        asyncio.run(runner.run())
    else:
        try:
            asyncio.run(run_app())
        except (KeyboardInterrupt, SystemExit):
            print("\nПриложение остановлено пользователем.")


if __name__ == "__main__":
    main()