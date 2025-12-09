# db.py
import os
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI")
client = MongoClient(MONGODB_URI)
db = client.get_default_database()

users_col = db["users"]            # { tg_id, balance, created_at }
groups_col = db["groups"]          # { group_link, requested_by, year, price, status, created_at }
withdraws_col = db["withdraws"]    # { tg_id, amount, address, status, created_at }
config_col = db["config"]          # stores sessions & price configs

def get_admins():
    raw = os.getenv("ADMINS", "")
    if not raw:
        return []
    return [int(x.strip()) for x in raw.split(",") if x.strip()]
