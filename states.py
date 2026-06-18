from aiogram.fsm.state import State, StatesGroup


class PaymentStates(StatesGroup):
    waiting_screenshot = State()


class EpisodeRequestStates(StatesGroup):
    waiting_serial = State()
    waiting_date = State()


class SupportStates(StatesGroup):
    waiting_message = State()


class AdminStates(StatesGroup):
    broadcast_message = State()
    lookup_user = State()
    grant_vip_user = State()
    delete_episode_serial = State()
    reply_support = State()
