# routers/verify_router.py
import re
from aiogram import Router, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from userbot_manager import active_clients, load_session_from_string
from db import groups_col, config_col, users_col
from ownership import get_price_for_year
from datetime import datetime

router = Router()

LINK_RE = re.compile(r"(t\.me\/[^\s]+|telegram\.me\/[^\s]+|joinchat\/[^\s]+)")

async def ensure_clients_loaded():
    # try to load sessions from DB into active_clients
    for acc in ("1","2"):
        conf = config_col.find_one({"_id": f"session_{acc}"})
        if conf and conf.get("session") and int(acc) not in active_clients:
            await load_session_from_string(int(acc), conf.get("session"))

@router.message()
async def handle_any_message(msg: types.Message):
    text = (msg.text or "").strip()
    if not text:
        return
    m = LINK_RE.search(text)
    if not m:
        return  # ignore non-links
    link = m.group(0)
    await msg.reply("Processing link... I'll try to join with user accounts and compute price. Please wait.")
    await ensure_clients_loaded()
    # try with first available client
    price_info = None
    year = None
    # prefer client 1 then 2
    for acc_num in (1,2):
        client = active_clients.get(acc_num)
        if not client:
            continue
        try:
            # try to get earliest year
            yr = await client.get_entity(link)
            # compute earliest message year
            from userbot_manager import earliest_message_year, join_group_by_link
            # attempt join (safe)
            try:
                ok, msg_join = await join_group_by_link(client, link)
            except Exception:
                ok, msg_join = (False, "join-failed")
            year = await earliest_message_year(client, link)
            base_price = get_price_for_year(year)
            price_info = {"year": year, "price": base_price, "used_account": acc_num}
            break
        except Exception:
            continue
    if not price_info:
        await msg.reply("Failed to fetch group info with our accounts. Ensure sessions are set and the link is correct or public.")
        return
    # save a pending group request
    groups_col.insert_one({
        "group_link": link,
        "requested_by": msg.from_user.id,
        "year": price_info["year"],
        "price": price_info["price"],
        "status": "pending",
        "created_at": datetime.utcnow()
    })
    kb = InlineKeyboardMarkup().add(InlineKeyboardButton("I gave ownership", callback_data=f"verify|{link}"))
    await msg.reply(f"Group year: {price_info['year']}\nEstimated price: {price_info['price']}\nIf you have given ownership to one of our accounts, press below:", reply_markup=kb)

@router.callback_query(lambda c: c.data and c.data.startswith("verify|"))
async def cb_verify(cq: types.CallbackQuery):
    data = cq.data.split("|",1)[1]
    link = data
    await cq.answer("Verifying ownership...")
    await ensure_clients_loaded()
    verified = False
    for acc_num, client in active_clients.items():
        try:
            ok = await client.get_entity(link)
            # use user id of the requester
            from userbot_manager import is_user_group_owner
            if await is_user_group_owner(client, link, cq.from_user.id):
                verified = True
                break
        except Exception:
            continue
    if verified:
        g = groups_col.find_one({"group_link": link, "requested_by": cq.from_user.id})
        price = g.get("price", 0.0) if g else 0.0
        users_col.update_one({"tg_id": cq.from_user.id}, {"$inc": {"balance": price}}, upsert=True)
        groups_col.update_one({"group_link": link}, {"$set": {"status":"verified", "verified_at": datetime.utcnow()}})
        await cq.message.answer(f"Ownership confirmed ✅. {price} has been added to your balance.")
    else:
        await cq.message.answer("Ownership not found. Make sure you gave ownership to one of the user accounts and try again.")
