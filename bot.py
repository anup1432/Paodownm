# bot.py
import os
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from dotenv import load_dotenv
from db import users_col, groups_col, withdraws_col, get_admins
from userbot_manager import start_clients, clients
from ownership import compute_group_price, set_price_for_year, get_price_for_year
from telethon.errors import FloodWaitError

load_dotenv()
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN")
bot = Bot(TG_BOT_TOKEN)
dp = Dispatcher()

# start telethon clients on bot startup
@dp.on_startup
async def on_startup():
    await start_clients()

# Basic menu keyboard
def main_menu():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(InlineKeyboardButton("Profile", callback_data="profile"),
           InlineKeyboardButton("My Balance", callback_data="balance"))
    kb.add(InlineKeyboardButton("Price", callback_data="price"),
           InlineKeyboardButton("Withdraw", callback_data="withdraw"))
    kb.add(InlineKeyboardButton("Support", callback_data="support"))
    return kb

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.reply("Assalamualaikum — Ownership verification bot. Group link bhejo ya /help dekho.", reply_markup=main_menu())

@dp.message()
async def any_message(message: types.Message):
    # If message is a group link (contains t.me/ or telegram.me)
    text = message.text.strip()
    if "t.me/" in text or "telegram.me/" in text or "joinchat/" in text:
        await message.reply("Processing link... I will ask my accounts to join and verify. Please wait.")
        # Try to let both userbot accounts join and compute price
        results = []
        for client in clients:
            try:
                ok, msg = await join_group_by_link(client, text)
                results.append((ok, msg))
            except Exception as e:
                results.append((False, str(e)))
        # Now compute price using first client
        try:
            res = await compute_group_price(clients[0], text)
            year = res["year"]; price = res["price"]
            # save pending verification
            groups_col.insert_one({
                "group_link": text,
                "requested_by": message.from_user.id,
                "year": year,
                "price": price,
                "status": "pending",
                "created_at": types.datetime.datetime.utcnow()
            })
            kb = InlineKeyboardMarkup().add(InlineKeyboardButton("I gave ownership", callback_data=f"verify|{text}"))
            await message.reply(f"Detected group year: {year}\nEstimated price: {price}\nAgar tumne ownership de di ho to click karo:", reply_markup=kb)
        except Exception as e:
            await message.reply("Price compute failed: " + str(e))
    else:
        await message.reply("Please send the group invite/link for verification or use the menu.", reply_markup=main_menu())

# Callback handlers (buttons)
@dp.callback_query()
async def cb_handler(cb: types.CallbackQuery):
    data = cb.data
    if data == "profile":
        user = users_col.find_one({"tg_id": cb.from_user.id}) or {}
        bal = user.get("balance", 0)
        await cb.message.edit_text(f"Profile:\nUser: {cb.from_user.full_name}\nBalance: {bal}", reply_markup=main_menu())
    elif data == "balance":
        user = users_col.find_one({"tg_id": cb.from_user.id}) or {}
        bal = user.get("balance", 0)
        await cb.answer(f"Tera balance: {bal}")
    elif data == "price":
        # show admin-set price table for quick view
        cfg = config_col.find_one({"_id":"prices"}) or {}
        by_year = cfg.get("by_year", {})
        text = "Prices by year:\n" + "\n".join([f"{y}: {p}" for y,p in by_year.items()])
        await cb.message.answer(text or "No prices set yet.")
    elif data.startswith("verify|"):
        link = data.split("|",1)[1]
        await cb.answer("Verifying ownership, please wait...")
        # check using telethon clients whether requestor is owner
        requester_id = cb.from_user.id
        verified = False
        for c in clients:
            try:
                ok = await is_user_group_owner(c, link, requester_id)
                if ok:
                    verified = True
                    break
            except Exception as e:
                continue
        if verified:
            # credit user balance with price
            g = groups_col.find_one({"group_link": link})
            price = g.get("price", 0) if g else 0
            users_col.update_one({"tg_id": requester_id}, {"$inc":{"balance": price}}, upsert=True)
            groups_col.update_one({"group_link": link}, {"$set":{"status":"verified","verified_at": types.datetime.datetime.utcnow()}})
            await cb.message.answer(f"Ownership confirmed ✅. {price} added to your balance.")
        else:
            await cb.message.answer("Ownership NOT found. Ensure you are the group creator/owner and try again or give admin rights to the userbot accounts for verification.")

# Admin commands: /setprice <year> <price>
@dp.message(Command("setprice"))
async def cmd_setprice(message: types.Message, args: types.Args):
    if message.from_user.id not in get_admins():
        await message.reply("Not authorized.")
        return
    try:
        year = args[0]
        price = float(args[1])
        set_price_for_year(year, price)
        await message.reply(f"Price for {year} set to {price}")
    except Exception as e:
        await message.reply("Usage: /setprice <year> <price>")

# /withdraw flow (user pressing Withdraw)
@dp.callback_query(text="withdraw")
async def cb_withdraw(cb: types.CallbackQuery):
    user = users_col.find_one({"tg_id": cb.from_user.id}) or {}
    bal = user.get("balance", 0)
    if bal <= 0:
        await cb.answer("No balance to withdraw.")
        return
    await cb.message.answer("Enter withdrawal amount and crypto address separated by newline (e.g. `100\n0xabc...`):")

    @dp.message()
    async def collect_withdraw(m: types.Message):
        try:
            amt, addr = m.text.splitlines()[:2]
            amt = float(amt.strip())
            if amt > bal:
                await m.reply("Amount > balance.")
                return
            # store withdraw request
            withdraws_col.insert_one({
                "tg_id": m.from_user.id,
                "amount": amt,
                "address": addr.strip(),
                "status": "pending",
                "created_at": types.datetime.datetime.utcnow()
            })
            users_col.update_one({"tg_id": m.from_user.id}, {"$inc":{"balance": -amt}})
            # notify admin channel with accept/decline buttons
            kb = InlineKeyboardMarkup().add(
                InlineKeyboardButton("Accept", callback_data=f"waccept|{m.from_user.id}"),
                InlineKeyboardButton("Decline", callback_data=f"wdecline|{m.from_user.id}")
            )
            await bot.send_message(os.getenv("WITHDRAW_CHANNEL_ID"), f"Withdraw request from {m.from_user.id}: {amt} to {addr}", reply_markup=kb)
            await m.reply("Withdraw request submitted; admin will review.")
        except Exception as e:
            await m.reply("Invalid format. Provide amount and address in two lines.")

# Admin accept/decline withdraw
@dp.callback_query(lambda c: c.data and c.data.startswith("waccept"))
async def cb_waccept(cb: types.CallbackQuery):
    if cb.from_user.id not in get_admins():
        await cb.answer("Not authorized.")
        return
    parts = cb.data.split("|")
    uid = int(parts[1])
    withdraw = withdraws_col.find_one_and_update({"tg_id":uid, "status":"pending"}, {"$set":{"status":"accepted","handled_by":cb.from_user.id}})
    if withdraw:
        await cb.message.edit_text("Withdraw accepted and will be processed.")
        # Here: place automated transfer instructions or manual process.
        await bot.send_message(uid, f"Your withdraw of {withdraw['amount']} accepted. Processing soon.")
    else:
        await cb.answer("No pending withdraw found.")

@dp.callback_query(lambda c: c.data and c.data.startswith("wdecline"))
async def cb_wdecline(cb: types.CallbackQuery):
    if cb.from_user.id not in get_admins():
        await cb.answer("Not authorized.")
        return
    parts = cb.data.split("|")
    uid = int(parts[1])
    withdraw = withdraws_col.find_one_and_update({"tg_id":uid, "status":"pending"}, {"$set":{"status":"declined","handled_by":cb.from_user.id}})
    if withdraw:
        # refund balance
        users_col.update_one({"tg_id": uid}, {"$inc":{"balance": withdraw["amount"]}})
        await cb.message.edit_text("Withdraw declined. Amount refunded.")
        await bot.send_message(uid, "Your withdraw request was declined; amount refunded.")
    else:
        await cb.answer("No pending withdraw found.")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("bot:dp", host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
