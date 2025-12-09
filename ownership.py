# ownership.py
from db import groups_col, config_col
from userbot_manager import earliest_message_year, is_user_group_owner
from datetime import datetime

DEFAULT_BASE_PRICE_BY_YEAR = {y: 10 for y in range(2016, 2025)}  # default per-year price (example INR/UNIT)

def get_price_for_year(year):
    cfg = config_col.find_one({"_id": "prices"})
    if cfg and "by_year" in cfg:
        return cfg["by_year"].get(str(year), DEFAULT_BASE_PRICE_BY_YEAR.get(year, 0))
    return DEFAULT_BASE_PRICE_BY_YEAR.get(year, 0)

def set_price_for_year(year, price):
    config_col.update_one({"_id":"prices"}, {"$set":{f"by_year.{year}": price}}, upsert=True)

async def compute_group_price(client, group_entity):
    year = await earliest_message_year(client, group_entity)
    base = get_price_for_year(year)
    # Example: price = base * 1.0 (you can add member-based multipliers)
    return {"year": year, "price": base}
