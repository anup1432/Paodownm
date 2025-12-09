# bot_season.py
import asyncio
from aiogram import Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from season_fsm import SeasonStates
from db import config_col, get_admins
from userbot_manager import create_temporary_client, temp_session_creations, finalize_session, temp_session_creations as TCRE, active_clients

router = Router()

@router.message(Command("season"))
async def cmd_season_start(message: types.Message, state: FSMContext):
    if message.from_user.id not in get_admins():
        await message.reply("❌ Not authorized.")
        return
    parts = message.text.split()
    if len(parts) < 2:
        await message.reply("Usage: /season <1|2>\nExample: /season 1")
        return
    acc = parts[1].strip()
    if acc not in ("1","2"):
        await message.reply("Account must be 1 or 2.")
        return
    await state.update_data(account=int(acc))
    await message.reply("📱 Send the phone number you want to login (include country code). Example: +91XXXXXXXXXX")
    await state.set_state(SeasonStates.awaiting_phone)

@router.message(SeasonStates.awaiting_phone)
async def season_phone(message: types.Message, state: FSMContext):
    data = await state.get_data()
    acc = data["account"]
    phone = message.text.strip()
    # create temporary client and send code request
    try:
        client = await create_temporary_client(phone)
    except Exception as e:
        await message.reply("❌ Failed to create temp client: " + str(e))
        await state.clear()
        return
    # store temp
    temp_session_creations[message.from_user.id] = {"account": acc, "phone": phone, "client": client}
    await state.update_data(phone=phone)
    await message.reply("✉️ OTP sent by Telegram. Please send the OTP you received.")
    await state.set_state(SeasonStates.awaiting_otp)

@router.message(SeasonStates.awaiting_otp)
async def season_otp(message: types.Message, state: FSMContext):
    entry = temp_session_creations.get(message.from_user.id)
    if not entry:
        await message.reply("Session expired or not started. Please run /season again.")
        await state.clear()
        return
    otp = message.text.strip()
    client = entry["client"]
    phone = entry["phone"]
    acc = entry["account"]
    try:
        # Attempt to sign in
        await client.sign_in(phone=phone, code=otp)
    except Exception as e:
        # If 2FA required
        if "SESSION_PASSWORD_NEEDED" in str(e) or isinstance(e, Exception):
            # Telethon raises SessionPasswordNeededError class; check:
            from telethon.errors import SessionPasswordNeededError
            if isinstance(e, SessionPasswordNeededError) or "SESSION_PASSWORD_NEEDED" in str(e):
                await message.reply("🔑 Two-step verification enabled. Please send the 2FA password now.")
                await state.set_state(SeasonStates.awaiting_2fa)
                # store otp too
                entry["otp"] = otp
                temp_session_creations[message.from_user.id] = entry
                return
        # Other errors
        await message.reply("❌ Sign-in error: " + str(e))
        await client.disconnect()
        temp_session_creations.pop(message.from_user.id, None)
        await state.clear()
        return

    # success: save session string
    session_str = await finalize_session(client, acc)
    # store in DB under config_col
    config_col.update_one({"_id": f"session_{acc}"}, {"$set": {"session": session_str}}, upsert=True)
    temp_session_creations.pop(message.from_user.id, None)
    await message.reply("✅ Session created and saved as session_{}.".format(acc))
    await state.clear()

@router.message(SeasonStates.awaiting_2fa)
async def season_2fa(message: types.Message, state: FSMContext):
    entry = temp_session_creations.get(message.from_user.id)
    if not entry:
        await message.reply("Session expired. Start /season again.")
        await state.clear()
        return
    password = message.text.strip()
    client = entry["client"]
    acc = entry["account"]
    try:
        await client.sign_in(password=password)
    except Exception as e:
        await message.reply("❌ 2FA sign-in failed: " + str(e))
        await client.disconnect()
        temp_session_creations.pop(message.from_user.id, None)
        await state.clear()
        return
    # success
    session_str = await finalize_session(client, acc)
    config_col.update_one({"_id": f"session_{acc}"}, {"$set": {"session": session_str}}, upsert=True)
    temp_session_creations.pop(message.from_user.id, None)
    await message.reply("✅ Session created with 2FA and saved as session_{}.".format(acc))
    await state.clear()
