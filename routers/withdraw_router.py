# routers/withdraw_router.py
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from db import users_col, withdraws_col, config_col, get_admins
from withdraws import create_withdraw_request, accept_withdraw, decline_withdraw
import os

router = Router()

@router.message(Command("withdraw"))
async def cmd_withdraw(msg):
    user = users_col.find_one({"tg_id": msg.from_user.id}) or {}
    bal = float(user.get("balance", 0.0))
    if bal <= 0:
        await msg.reply("You have zero balance.")
        return
    await msg.reply("Send amount and crypto address in two lines:\nExample:\n100\n0xabc...")

    # next message will be parsed by a small inline handler attached to router
    @router.message()
    async def handle_amount(m):
        if m.from_user.id != msg.from_user.id:
            return
        parts = m.text.strip().splitlines()
        if len(parts) < 2:
            await m.reply("Invalid format. Provide amount and address in two lines.")
            return
        try:
            amt = float(parts[0].strip())
        except:
            await m.reply("Invalid amount.")
            return
        addr = parts[1].strip()
        if amt > bal:
            await m.reply("Amount exceeds your balance.")
            return
        # create withdraw request
        create_withdraw_request(m.from_user.id, amt, addr)
        # deduct balance
        users_col.update_one({"tg_id": m.from_user.id}, {"$inc": {"balance": -amt}})
        await m.reply("Withdraw request submitted. Admin will approve it.")

        # notify admin channel
        channel = os.getenv("WITHDRAW_CHANNEL_ID")
        kb = InlineKeyboardMarkup().add(
            InlineKeyboardButton("Accept", callback_data=f"waccept|{m.from_user.id}"),
            InlineKeyboardButton("Decline", callback_data=f"wdecline|{m.from_user.id}")
        )
        from bot import bot as main_bot
        await main_bot.send_message(channel, f"Withdraw request from {m.from_user.id}: {amt} to {addr}", reply_markup=kb)

@router.callback_query(lambda c: c.data and c.data.startswith("waccept"))
async def cb_waccept(cq):
    uid = int(cq.data.split("|")[1])
    if cq.from_user.id not in get_admins():
        await cq.answer("Not authorized.")
        return
    w = accept_withdraw(uid, cq.from_user.id)
    if w:
        await cq.message.edit_text("Withdraw accepted.")
        from bot import bot as main_bot
        await main_bot.send_message(uid, f"Your withdraw of {w['amount']} accepted by admin.")
    else:
        await cq.answer("No pending withdraw found.")

@router.callback_query(lambda c: c.data and c.data.startswith("wdecline"))
async def cb_wdecline(cq):
    uid = int(cq.data.split("|")[1])
    if cq.from_user.id not in get_admins():
        await cq.answer("Not authorized.")
        return
    w = decline_withdraw(uid, cq.from_user.id)
    if w:
        await cq.message.edit_text("Withdraw declined and refunded.")
        from bot import bot as main_bot
        await main_bot.send_message(uid, f"Your withdraw request of {w['amount']} was declined by admin. Amount refunded.")
    else:
        await cq.answer("No pending withdraw found.")
