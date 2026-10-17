import asyncio
import logging
from bot.bot_service import BotRunner
import config

logging.basicConfig(level=logging.INFO)

async def main():
    runner = BotRunner(token=config.BOT_TOKEN, db_path=config.DB_PATH)
    await runner.run()

if __name__ == "__main__":
    asyncio.run(main())