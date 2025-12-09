# ownership.py
from db import config_col
from datetime import datetime

DEFAULT_BASE_PRICE_BY_YEAR = {str(y): 10 for y in range(2016, 2025)}  # default units

def get_price_for_year(year):
    cfg = config_col.find_one({"_id": "prices"})
    if cfg and "by_year" in cfg:
        return float(cfg["by_year"].get(str(year), DEFAULT_BASE_PRICE_BY_YEAR.get(str(year), 0)))
    return float(DEFAULT_BASE_PRICE_BY_YEAR.get(str(year), 0))

def set_price_for_year(year, price):
    # year is string or int
    y = str(year)
    config_col.update_one({"_id":"prices"}, {"$set": {f"by_year.{y}": float(price)}}, upsert=True)

def get_all_prices():
    cfg = config_col.find_one({"_id":"prices"}) or {}
    return cfg.get("by_year", DEFAULT_BASE_PRICE_BY_YEAR.copy())
