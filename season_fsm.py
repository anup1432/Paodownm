# season_fsm.py
from aiogram.fsm.state import StatesGroup, State

class SeasonStates(StatesGroup):
    awaiting_account_number = State()
    awaiting_phone = State()
    awaiting_otp = State()
    awaiting_2fa = State()
