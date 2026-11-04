import asyncio
from gui.web_app import WebDashboardApp
import config

async def main():
    server = WebDashboardApp(
        db_path=config.DB_PATH,
        token=config.BOT_TOKEN
    )
    await server.run()

if __name__ == "__main__":
    asyncio.run(main())