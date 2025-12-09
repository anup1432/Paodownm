# userbot_manager.py
import os
from dotenv import load_dotenv
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError, UserAlreadyParticipantError
from telethon.tl.types import ChannelParticipantsAdmins
from datetime import datetime
import asyncio

load_dotenv()
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")

# Active telethon clients loaded from DB sessions
active_clients = {}   # account_num -> TelegramClient instance

# Temporary state while creating session via /season
temp_session_creations = {}  # admin_user_id -> { "account": 1, "phone": "+91...", "client": client }

async def load_session_from_string(account_num, session_string):
    """
    Load a TelegramClient from saved string and store in active_clients.
    """
    if not session_string:
        return None
    session = StringSession(session_string)
    client = TelegramClient(session, API_ID, API_HASH)
    await client.connect()
    # optionally verify authorized
    if not await client.is_user_authorized():
        await client.disconnect()
        return None
    active_clients[account_num] = client
    return client

async def create_temporary_client(phone):
    """
    Create a temporary client and request code. Return client.
    """
    session = StringSession()
    client = TelegramClient(session, API_ID, API_HASH)
    await client.connect()
    # send code request (telethon will choose method)
    await client.send_code_request(phone)
    return client

async def finalize_session(client, account_num):
    """
    Save client as active and return session string.
    """
    session_str = client.session.save()
    active_clients[account_num] = client
    return session_str

async def join_group_by_link(client, link):
    try:
        # telethon accepts username or invite link; use client.get_entity if needed
        await client(telethon.tl.functions.channels.JoinChannelRequest(link))
        return True, "joined"
    except UserAlreadyParticipantError:
        return True, "already"
    except Exception as e:
        return False, str(e)

async def is_user_group_owner(client, group_entity, target_user_id):
    try:
        admins = await client.get_participants(group_entity, filter=ChannelParticipantsAdmins)
        for a in admins:
            if getattr(a, "creator", False) or getattr(a, "is_creator", False):
                if a.id == target_user_id:
                    return True
            # fallback: if id matches and has admin rights, accept
            if a.id == target_user_id:
                return True
    except Exception:
        pass
    return False

async def earliest_message_year(client, group_entity):
    try:
        # Reverse iteration to get earliest message quickly (limit may be 1)
        async for msg in client.iter_messages(group_entity, reverse=True, limit=1):
            if msg and msg.date:
                return msg.date.year
    except Exception:
        pass
    return datetime.utcnow().year
