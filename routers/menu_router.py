# routers/menu_router.py
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from db import users_col, get_admins

router = Router()

def main_menu_kb():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(InlineKeyboardButton("Profile", callback_data="menu:profile"),
           InlineKeyboardButton("My Balance", callback_data="menu:balance"))
    kb.add(InlineKeyboardButton("Price", callback_data="menu:price"),
           InlineKeyboardButton("Withdraw", callback_data="menu:withdraw"))
    kb.add(InlineKeyboardButton("Support", callback_data="menu:support"))
    return kb

@router.message(Command("start"))
async def cmd_start(msg):
    await msg.reply("Welcome! Send me a group invite/link to verify ownership or use the menu.", reply_markup=main_menu_kb())

@router.callback_query(lambda c: c.data and c.data.startswith("menu:"))
async def cb_menu(cq):
    data = cq.data.split(":")[1]
    if data == "profile":
        user = users_col.find_one({"tg_id": cq.from_user.id}) or {}
        bal = user.get("balance", 0.0)
        await cq.message.edit_text(f"Profile:\nName: {cq.from_user.full_name}\nBalance: {bal}")
    elif data == "balance":
        user = users_col.find_one({"tg_id": cq.from_user.id}) or {}
        bal = user.get("balance", 0.0)
        await cq.answer(f"Your balance: {bal}")
    elif data == "price":
        from ownership import get_all_prices
        by_year = get_all_prices()
        text = "Prices:\n" + "\n".join([f"{y}: {p}" for y,p in sorted(by_year.items())])
        await cq.message.answer(text)
    elif data == "withdraw":
        await cq.message.answer("To withdraw, click /withdraw or press Withdraw from commands.")
    elif data == "support":
        await cq.message.answer("Contact support: send message and tag @owner or use admin channel.")
