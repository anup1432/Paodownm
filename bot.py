# bot.py
import os
import logging
import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dotenv import load_dotenv
from pymongo import MongoClient
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

load_dotenv()

# -------------------------------
# CONFIG
# -------------------------------
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN", "8435658476:AAEBER1zaUbZTJSRFtCJv2fRl24WqXDQSr4")
ADMIN_ID = 1804574038
MONGO_URL = os.getenv("MONGO_URL", "srv://cap1432:cap1432@cluster0.yllxk9g.mongodb.net/botydb?retryWrites=true&w=majority&appName=Cluster0")

# Telethon linked accounts for ownership check
API_ID = 38683063
API_HASH = os.getenv("API_HASH", "dfecebe3a34c2f1974ba11e9aa32d66a")
SESSION1 = "session1"  # file based
SESSION2 = "session2"

# -------------------------------
# LOGGING
# -------------------------------
logging.basicConfig(level=logging.INFO)

# -------------------------------
# DATABASE
# -------------------------------
client = MongoClient(MONGO_URL)
db = client['botydb']
users_col = db['users']
withdraw_col = db['withdraw']
price_col = db['price']

# Default price setup if empty
if price_col.count_documents({}) == 0:
    price_col.insert_one({"old_group_price": 100})  # default 100 units

# -------------------------------
# TELEGRAM CLIENTS (Telethon)
# -------------------------------
linked_client1 = TelegramClient(SESSION1, API_ID, API_HASH)
linked_client2 = TelegramClient(SESSION2, API_ID, API_HASH)

async def start_linked_clients():
    await linked_client1.start()
    await linked_client2.start()

# -------------------------------
# BOT SETUP
# -------------------------------
bot = Bot(token=TG_BOT_TOKEN)
dp = Dispatcher()

# -------------------------------
# HELPERS
# -------------------------------
def get_user_keyboard(user_id):
    kb = InlineKeyboardBuilder()
    kb.button(text="Profile", callback_data="profile")
    kb.button(text="My Balance", callback_data="balance")
    kb.button(text="Price", callback_data="price")
    kb.button(text="Withdraw", callback_data="withdraw")
    kb.button(text="Support", callback_data="support")
    return kb.as_markup()

def get_admin_keyboard():
    kb = InlineKeyboardBuilder()
    kb.button(text="Approve Withdraw", callback_data="approve_withdraw")
    kb.button(text="Decline Withdraw", callback_data="decline_withdraw")
    return kb.as_markup()

# -------------------------------
# COMMANDS
# -------------------------------
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user = users_col.find_one({"user_id": message.from_user.id})
    if not user:
        users_col.insert_one({"user_id": message.from_user.id, "balance": 0, "ownership_verified": False})
    await message.answer("Welcome! Use buttons below.", reply_markup=get_user_keyboard(message.from_user.id))

@dp.message(Command("season"))
async def cmd_season(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.reply("You are not authorized.")
        return
    await message.reply("Enter OTP for admin login (simulate for now).")

@dp.message(Command("price"))
async def cmd_price(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.reply("Unauthorized")
        return
    price = price_col.find_one({})
    await message.reply(f"Current old group price: {price['old_group_price']} units. Use /setprice <amount> to change.")

@dp.message(Command("setprice"))
async def cmd_setprice(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.reply("Unauthorized")
        return
    try:
        amount = int(message.text.split()[1])
        price_col.update_one({}, {"$set": {"old_group_price": amount}})
        await message.reply(f"Old group price updated to {amount} units.")
    except:
        await message.reply("Usage: /setprice <amount>")

# -------------------------------
# CALLBACK HANDLERS (Buttons)
# -------------------------------
@dp.callback_query(F.data == "profile")
async def cb_profile(callback: types.CallbackQuery):
    user = users_col.find_one({"user_id": callback.from_user.id})
    await callback.message.edit_text(f"Profile:\nUser ID: {callback.from_user.id}\nOwnership Verified: {user.get('ownership_verified', False)}\nBalance: {user.get('balance',0)} units", reply_markup=get_user_keyboard(callback.from_user.id))

@dp.callback_query(F.data == "balance")
async def cb_balance(callback: types.CallbackQuery):
    user = users_col.find_one({"user_id": callback.from_user.id})
    await callback.message.edit_text(f"Your balance: {user.get('balance',0)} units", reply_markup=get_user_keyboard(callback.from_user.id))

@dp.callback_query(F.data == "price")
async def cb_price(callback: types.CallbackQuery):
    price = price_col.find_one({})
    await callback.message.edit_text(f"Old group price: {price['old_group_price']} units", reply_markup=get_user_keyboard(callback.from_user.id))

@dp.callback_query(F.data == "withdraw")
async def cb_withdraw(callback: types.CallbackQuery):
    await callback.message.edit_text("Send your Polygon BEP20 or Binance C-wallet address to withdraw:")

@dp.callback_query(F.data == "support")
async def cb_support(callback: types.CallbackQuery):
    await bot.send_message(ADMIN_ID, f"User @{callback.from_user.username} ({callback.from_user.id}) requested support.")
    await callback.message.edit_text("Support request sent to admin.", reply_markup=get_user_keyboard(callback.from_user.id))

# -------------------------------
# OWNERSHIP VERIFICATION (Simulated)
# -------------------------------
async def verify_ownership(user_id, group_link):
    """
    Simulated: Use linked_client1 & linked_client2 to join group & verify ownership.
    On success, add balance automatically.
    """
    # Simulate ownership check
    await asyncio.sleep(2)
    users_col.update_one({"user_id": user_id}, {"$set": {"ownership_verified": True}})
    price = price_col.find_one({})
    users_col.update_one({"user_id": user_id}, {"$inc": {"balance": price['old_group_price']}})
    await bot.send_message(user_id, f"Ownership verified! {price['old_group_price']} units added to your balance.")

# -------------------------------
# START BOT
# -------------------------------
async def main():
    await start_linked_clients()
    print("Linked clients started")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
