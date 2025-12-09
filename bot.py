# bot.py
import asyncio
import os
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv
from db import config_col
from userbot_manager import load_session_from_string
from routers.menu_router import router as menu_router
from routers.verify_router import router as verify_router
from routers.withdraw_router import router as withdraw_router
from bot_season import router as season_router

load_dotenv()

TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN")
bot = Bot(TG_BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# include routers
dp.include_router(menu_router)
dp.include_router(verify_router)
dp.include_router(withdraw_router)
dp.include_router(season_router)

async def startup():
    # load saved telethon sessions from DB (session_1, session_2)
    for acc in ("1","2"):
        conf = config_col.find_one({"_id": f"session_{acc}"})
        if conf and conf.get("session"):
            await load_session_from_string(int(acc), conf.get("session"))
    print("Startup complete. Telethon sessions loaded if present.")

async def main():
    await startup()
    try:
        print("Starting bot polling...")
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
