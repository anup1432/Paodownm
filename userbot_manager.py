# userbot_manager.py
from telethon import TelegramClient, events
import os
from dotenv import load_dotenv
from telethon.tl.types import ChannelParticipantsAdmins
from telethon.errors import SessionPasswordNeededError, UserAlreadyParticipantError
from datetime import datetime

load_dotenv()
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")

# session strings from .env
S1 = os.getenv("USER_SESSION_1")
S2 = os.getenv("USER_SESSION_2")

clients = []
if S1:
    clients.append(TelegramClient(StringSession(S1), API_ID, API_HASH))
if S2:
    clients.append(TelegramClient(StringSession(S2), API_ID, API_HASH))

async def start_clients():
    for c in clients:
        await c.start()
    return clients

async def join_group_by_link(client, link):
    try:
        await client(JoinChannelRequest(link))
        return True, "joined"
    except UserAlreadyParticipantError:
        return True, "already"
    except Exception as e:
        return False, str(e)

async def is_user_group_owner(client, group_entity, target_user_id):
    """
    Check if target_user_id is the creator of group_entity.
    """
    admins = await client.get_participants(group_entity, filter=ChannelParticipantsAdmins)
    for a in admins:
        # Telethon admin object may have .creator True or a.participant.role
        try:
            if getattr(a, 'creator', False) or getattr(a, 'is_creator', False):
                if a.id == target_user_id:
                    return True
        except:
            # fallback check: check admin rights equality
            if a.id == target_user_id:
                # cannot be sure it's creator; still flag True if matches
                return True
    return False

async def earliest_message_year(client, group_entity):
    # fetch earliest message by scanning backwards - careful with rate limits.
    async for msg in client.iter_messages(group_entity, reverse=True, limit=1):
        if msg and msg.date:
            return msg.date.year
    # fallback: return current year
    return datetime.utcnow().year
