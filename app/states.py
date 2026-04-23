from aiogram.fsm.state import State, StatesGroup


class SearchStates(StatesGroup):
    waiting_for_query = State()


class TopUpStates(StatesGroup):
    waiting_for_amount = State()
    waiting_for_asset = State()


class AddSellerStates(StatesGroup):
    waiting_for_identity = State()


class RemoveSellerStates(StatesGroup):
    waiting_for_identity = State()


class SellerAddProductStates(StatesGroup):
    waiting_for_category = State()
    waiting_for_subcategory = State()
    waiting_for_title = State()
    waiting_for_description = State()
    waiting_for_price = State()
    waiting_for_file = State()
    waiting_for_delivery_text = State()


class RejectProductStates(StatesGroup):
    waiting_for_reason = State()


class ResendProductStates(StatesGroup):
    waiting_for_buyer_identity = State()


class BroadcastStates(StatesGroup):
    waiting_for_message = State()
