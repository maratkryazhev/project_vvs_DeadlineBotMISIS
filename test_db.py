from database import AsyncDatabase, SyncDatabase
import asyncio

async def test():
    db = AsyncDatabase("test_deadlines.db")
    await db.init_db()
    print("база создана")

if __name__ == "__main__":
    asyncio.run(test())