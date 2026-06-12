from aiogram.fsm.state import State, StatesGroup


class RoomStates(StatesGroup):
    waiting_for_bet = State()


class WalletStates(StatesGroup):
    waiting_for_deposit_amount = State()
    waiting_for_withdraw_amount = State()
    waiting_for_promocode = State()


class AdminStates(StatesGroup):
    waiting_for_promocode = State()
    waiting_for_min_room = State()
    waiting_for_referral_percent = State()
    waiting_for_min_deposit = State()
    waiting_for_min_withdraw = State()
    waiting_for_required_channel = State()
    waiting_for_admin = State()
    waiting_for_balance_add = State()
    waiting_for_balance_remove = State()
