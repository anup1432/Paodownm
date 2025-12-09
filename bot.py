# bot.py
import os
import asyncio
import logging
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from telethon import TelegramClient, errors
from telethon.sessions import StringSession
from pymongo import MongoClient

load_dotenv()
logging.basicConfig(level=logging.INFO)

# -------------------------
# CONFIG (from env)
# -------------------------
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN")
API_ID = int(os.getenv("API_ID", "38683063"))
API_HASH = os.getenv("API_HASH")
MONGO_URL = os.getenv("MONGO_URL")
ADMIN_ID = int(os.getenv("ADMIN_ID", "1804574038"))

if not (TG_BOT_TOKEN and API_HASH and MONGO_URL):
    logging.error("Please set TG_BOT_TOKEN, API_HASH and MONGO_URL in .env")
    raise SystemExit("Missing env vars")

# -------------------------
# DATABASE
# -------------------------
mongo = MongoClient(MONGO_URL)
db = mongo["botydb"]
users_col = db["users"]
price_col = db["price"]
sessions_col = db["sessions"]   # store {name: "session1", session: "<string>"}
pending_col = db["pending"]     # temporary state for session creation

# default price
if price_col.count_documents({}) == 0:
    price_col.insert_one({"old_group_price": 100})

# -------------------------
# TELETHON CLIENTS (will be loaded from DB)
# -------------------------
linked_clients = {"session1": None, "session2": None}

async def load_linked_clients():
    """Load stored string sessions from DB and start clients."""
    for sname in ("session1", "session2"):
        doc = sessions_col.find_one({"name": sname})
        if doc and doc.get("session"):
            try:
                session_str = doc["session"]
                client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
                await client.start()
                linked_clients[sname] = client
                logging.info(f"Loaded linked client: {sname}")
            except Exception as e:
                logging.exception(f"Failed to start linked client {sname}: {e}")
        else:
            logging.info(f"No session stored for {sname}")

# -------------------------
# AIORAM BOT SETUP
# -------------------------
bot = Bot(token=TG_BOT_TOKEN)
dp = Dispatcher()

# Helper: user keyboard
def user_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="Profile", callback_data="profile")
    kb.button(text="My Balance", callback_data="balance")
    kb.button(text="Price", callback_data="price")
    kb.button(text="Withdraw", callback_data="withdraw")
    kb.button(text="Support", callback_data="support")
    return kb.as_markup()

# -------------------------
# COMMANDS
# -------------------------
@dp.message(Command("start"))
async def start_cmd(m: types.Message):
    uid = m.from_user.id
    if not users_col.find_one({"user_id": uid}):
        users_col.insert_one({"user_id": uid, "balance": 0, "ownership_verified": False})
    await m.answer("Welcome! Use buttons below.", reply_markup=user_kb())

# Admin-only: create session1/session2 interactively
def is_admin(uid:int):
    return uid == ADMIN_ID

@dp.message(Command("session1"))
async def session1_start(m: types.Message):
    if not is_admin(m.from_user.id):
        return await m.reply("Unauthorized.")
    # start creation flow for session1
    pending_col.update_one({"admin_id": m.from_user.id}, {"$set": {"stage": "await_phone", "which": "session1"}}, upsert=True)
    await m.reply("Enter phone number (international format, e.g. +9199xxxx...) for session1:")

@dp.message(Command("session2"))
async def session2_start(m: types.Message):
    if not is_admin(m.from_user.id):
        return await m.reply("Unauthorized.")
    pending_col.update_one({"admin_id": m.from_user.id}, {"$set": {"stage": "await_phone", "which": "session2"}}, upsert=True)
    await m.reply("Enter phone number (international format, e.g. +9199xxxx...) for session2:")

# Admin can set price
@dp.message(Command("setprice"))
async def set_price(m: types.Message):
    if not is_admin(m.from_user.id):
        return await m.reply("Unauthorized.")
    parts = m.text.strip().split()
    if len(parts) != 2:
        return await m.reply("Usage: /setprice <amount>")
    try:
        amt = int(parts[1])
        price_col.update_one({}, {"$set": {"old_group_price": amt}})
        await m.reply(f"Old group price set to {amt}")
    except:
        await m.reply("Invalid amount")

# User verify command (simple flow) - user provides group link, bot will try verification
@dp.message(Command("verify"))
async def verify_cmd(m: types.Message):
    # Usage: /verify <invite_link_or_chat_username_or_id>
    args = m.text.strip().split(maxsplit=1)
    if len(args) < 2:
        return await m.reply("Usage: /verify <group_invite_link_or_username_or_id>")
    target = args[1].strip()
    # Try to have linked clients check membership / join
    added_any = False
    errors_list = []
    for name, client in linked_clients.items():
        if client is None:
            errors_list.append(f"{name} not available")
            continue
        try:
            # try to join using invite link or username
            # Telethon supports client(JoinChannelRequest) but we use join via .join_channel
            try:
                await client(  # try to join
                    __import__("telethon").functions.channels.JoinChannelRequest(target)
                )
                added_any = True
            except Exception:
                # if invite link (t.me/joinchat/...) try ImportChatInviteRequest with hash
                try:
                    if "joinchat" in target or "t.me/+" in target:
                        # extract hash portion
                        h = target.rstrip("/").split("/")[-1]
                        await client(__import__("telethon").functions.messages.ImportChatInviteRequest(h))
                        added_any = True
                    else:
                        # fallback: get entity (might already be in)
                        _ = await client.get_entity(target)
                        added_any = True
                except Exception as e:
                    raise e
        except Exception as e:
            logging.exception("verify error")
            errors_list.append(f"{name}: {repr(e)}")
    if added_any:
        # mark user ownership_verified True and add price
        price = price_col.find_one({}) or {"old_group_price": 100}
        users_col.update_one({"user_id": m.from_user.id}, {"$set": {"ownership_verified": True}, "$inc": {"balance": price["old_group_price"]}})
        await m.reply(f"Ownership verified (attempt). {price['old_group_price']} units added to your balance.")
    else:
        await m.reply("Verification failed. Details: " + "; ".join(errors_list))

# -------------------------
# MESSAGE HANDLER (for admin session flow)
# -------------------------
@dp.message(F.text & (~F.command))
async def generic_text(m: types.Message):
    # Check pending for this admin
    pend = pending_col.find_one({"admin_id": m.from_user.id})
    if not pend:
        # normal user chat fallback
        return  # ignore or implement other flows
    stage = pend.get("stage")
    which = pend.get("which")
    text = m.text.strip()
    # Stage: awaiting phone
    if stage == "await_phone":
        phone = text
        # create temporary telethon client with blank session to send code
        tmp_session = StringSession()
        client = TelegramClient(tmp_session, API_ID, API_HASH)
        await client.connect()
        try:
            sent = await client.send_code(phone)
            # store state in pending: phone and temp session string (so we can sign_in)
            # We save the session object's data (it contains no auth yet)
            pending_col.update_one({"admin_id": m.from_user.id}, {"$set": {"stage": "await_code", "phone": phone, "tmp_session": client.session.save()}}, upsert=True)
            await m.reply("Code sent to that number. Please enter the code you received (OTP).")
        except errors.PhoneNumberInvalidError:
            await m.reply("Phone number invalid. Try again or cancel with /cancel.")
            await client.disconnect()
            return
        except Exception as e:
            await m.reply(f"Failed to send code: {e}")
            await client.disconnect()
            return
        # keep client connected until sign-in finished (we'll reconnect later using saved session string)
        await client.disconnect()
        return

    if stage == "await_code":
        code = text
        doc = pend
        phone = doc.get("phone")
        tmp_session_str = doc.get("tmp_session")
        if not phone or not tmp_session_str:
            pending_col.delete_one({"admin_id": m.from_user.id})
            return await m.reply("Session expired. Start again.")
        tmp_session = StringSession(tmp_session_str)
        client = TelegramClient(tmp_session, API_ID, API_HASH)
        await client.connect()
        try:
            # try sign in with code
            try:
                await client.sign_in(phone=phone, code=code)
            except errors.SessionPasswordNeededError:
                # two-factor enabled: ask for password
                pending_col.update_one({"admin_id": m.from_user.id}, {"$set": {"stage": "await_password"}}, upsert=True)
                await client.disconnect()
                return await m.reply("Two-step password enabled on this account. Send the password now.")
            except Exception as e:
                # maybe already signed in
                # try to check if authorized
                if not await client.is_user_authorized():
                    pending_col.delete_one({"admin_id": m.from_user.id})
                    await client.disconnect()
                    return await m.reply(f"Sign-in failed: {e}")
            # if reached here, sign-in succeeded
            # get session string
            full_session_str = client.session.save()
            # store into DB as which (session1/session2)
            if which not in ("session1", "session2"):
                which = doc.get("which", "session1")
            sessions_col.update_one({"name": which}, {"$set": {"name": which, "session": full_session_str}}, upsert=True)
            # cleanup pending
            pending_col.delete_one({"admin_id": m.from_user.id})
            await client.disconnect()
            # start or restart linked clients
            await load_linked_clients()
            await m.reply(f"{which} created and saved. Linked clients reloaded.")
            return
        except Exception as e:
            pending_col.delete_one({"admin_id": m.from_user.id})
            await client.disconnect()
            return await m.reply(f"Sign-in error: {e}")

    if stage == "await_password":
        password = text
        doc = pend
        phone = doc.get("phone")
        tmp_session_str = doc.get("tmp_session")
        which = doc.get("which", "session1")
        tmp_session = StringSession(tmp_session_str)
        client = TelegramClient(tmp_session, API_ID, API_HASH)
        await client.connect()
        try:
            await client.sign_in(password=password)
            full_session_str = client.session.save()
            sessions_col.update_one({"name": which}, {"$set": {"name": which, "session": full_session_str}}, upsert=True)
            pending_col.delete_one({"admin_id": m.from_user.id})
            await client.disconnect()
            await load_linked_clients()
            await m.reply(f"{which} created and saved (with 2FA). Linked clients reloaded.")
            return
        except Exception as e:
            pending_col.delete_one({"admin_id": m.from_user.id})
            await client.disconnect()
            return await m.reply(f"Password sign-in failed: {e}")

# Cancel command
@dp.message(Command("cancel"))
async def cancel_cmd(m: types.Message):
    pending_col.delete_many({"admin_id": m.from_user.id})
    await m.reply("Pending session creation canceled.")

# Simple callback handlers for buttons (profile, balance, price, withdraw, support)
@dp.callback_query(F.data == "profile")
async def cb_profile(cb: types.CallbackQuery):
    user = users_col.find_one({"user_id": cb.from_user.id}) or {}
    await cb.message.edit_text(f"Profile\nID: {cb.from_user.id}\nVerified: {user.get('ownership_verified', False)}\nBalance: {user.get('balance',0)}", reply_markup=user_kb())

@dp.callback_query(F.data == "balance")
async def cb_balance(cb: types.CallbackQuery):
    user = users_col.find_one({"user_id": cb.from_user.id}) or {}
    await cb.message.edit_text(f"Balance: {user.get('balance',0)}", reply_markup=user_kb())

@dp.callback_query(F.data == "price")
async def cb_price(cb: types.CallbackQuery):
    price = price_col.find_one({}) or {"old_group_price": 0}
    await cb.message.edit_text(f"Old group price: {price['old_group_price']}", reply_markup=user_kb())

@dp.callback_query(F.data == "withdraw")
async def cb_withdraw(cb: types.CallbackQuery):
    await cb.message.edit_text("Send your Polygon BEP20 or Binance C-wallet address to withdraw.", reply_markup=user_kb())

@dp.callback_query(F.data == "support")
async def cb_support(cb: types.CallbackQuery):
    await bot.send_message(ADMIN_ID, f"Support request from {cb.from_user.id} @{cb.from_user.username}")
    await cb.message.edit_text("Support request sent to admin.", reply_markup=user_kb())

# startup: load linked clients then start polling
async def on_startup():
    await load_linked_clients()
    logging.info("Startup complete. Bot is online.")

async def main():
    await on_startup()
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot stopped")
