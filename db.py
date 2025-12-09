# db.py
from pymongo import MongoClient
import os
from dotenv import load_dotenv
load_dotenv()

client = MongoClient(os.getenv("MONGODB_URI"))
db = client.get_default_database()

users_col = db["users"]            # stores user balances, linked tg id
groups_col = db["groups"]          # stores group verifications & pricing
withdraws_col = db["withdraws"]    # withdraw queue
config_col = db["config"]          # admin-set prices, base config

def get_admins():
    admins = os.getenv("ADMINS", "")
    return [int(x) for x in admins.split(",") if x.strip()]
