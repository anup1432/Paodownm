# withdraws.py
from db import withdraws_col, users_col
from datetime import datetime

def create_withdraw_request(tg_id, amount, address):
    withdraw = {
        "tg_id": tg_id,
        "amount": float(amount),
        "address": address,
        "status": "pending",
        "created_at": datetime.utcnow()
    }
    withdraws_col.insert_one(withdraw)
    return withdraw

def accept_withdraw(tg_id, admin_id):
    w = withdraws_col.find_one_and_update({"tg_id": tg_id, "status": "pending"}, {"$set": {"status": "accepted", "handled_by": admin_id}})
    return w

def decline_withdraw(tg_id, admin_id):
    w = withdraws_col.find_one_and_update({"tg_id": tg_id, "status": "pending"}, {"$set": {"status": "declined", "handled_by": admin_id}})
    if w:
        # refund
        users_col.update_one({"tg_id": tg_id}, {"$inc": {"balance": w["amount"]}})
    return w
