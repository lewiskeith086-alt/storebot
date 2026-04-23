from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.config import get_settings
from app.models import PaymentAsset, Product, Subcategory

settings = get_settings()


def persistent_main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text='Tools'), KeyboardButton(text='Logs')],
            [KeyboardButton(text='Docs'), KeyboardButton(text='Service')],
            [KeyboardButton(text='Tutorials'), KeyboardButton(text='Support')],
            [KeyboardButton(text='Wallet'), KeyboardButton(text='My Purchases')],
            [KeyboardButton(text='Referral')],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def seller_admin_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text='Add Product'), KeyboardButton(text='My Products')],
            [KeyboardButton(text='My Sales'), KeyboardButton(text='Buyers')],
            [KeyboardButton(text='Store Menu')],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def super_admin_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text='Products'), KeyboardButton(text='Sellers')],
            [KeyboardButton(text='Orders'), KeyboardButton(text='Finance')],
            [KeyboardButton(text='Broadcast'), KeyboardButton(text='Store Menu')],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def subcategory_keyboard(subcategories: list[Subcategory]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for sub in subcategories:
        builder.button(text=sub.label, callback_data=f'subcategory:{sub.id}')
    builder.button(text='⬅ Back', callback_data='nav:main')
    builder.adjust(2)
    return builder.as_markup()


def product_list_keyboard(products: list[Product]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for product in products:
        builder.button(text=product.title, callback_data=f'product:{product.id}')
    builder.button(text='⬅ Back', callback_data='nav:main')
    builder.adjust(1)
    return builder.as_markup()


def product_details_keyboard(product_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text='💳 Pay with Wallet', callback_data=f'buy:wallet:{product_id}')
    builder.button(text='🪙 Pay with Crypto', callback_data=f'buy:crypto:{product_id}')
    if settings.stars_enabled:
        builder.button(text='⭐ Pay with Stars', callback_data=f'buy:stars:{product_id}')
    builder.button(text='⬅ Back', callback_data='nav:main')
    builder.adjust(1)
    return builder.as_markup()


def crypto_asset_keyboard(order_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text='₿ BTC', callback_data=f'asset:{order_id}:{PaymentAsset.btc.value}')
    builder.button(text='💵 USDT (TRON)', callback_data=f'asset:{order_id}:{PaymentAsset.usdt_tron.value}')
    builder.button(text='⬅ Back', callback_data='nav:main')
    builder.adjust(1)
    return builder.as_markup()


def invoice_keyboard(payment_request_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ I've Paid", callback_data=f'invoice:refresh:{payment_request_id}')
    builder.button(text='🔄 Refresh Status', callback_data=f'invoice:refresh:{payment_request_id}')
    builder.button(text='❌ Cancel', callback_data=f'invoice:cancel:{payment_request_id}')
    builder.adjust(1)
    return builder.as_markup()


def wallet_home_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text='💰 Add Balance', callback_data='wallet:add')],
            [InlineKeyboardButton(text='⬅ Back', callback_data='nav:main')],
        ]
    )


def support_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text='📩 Contact Admin', url=f'https://t.me/{settings.support_username}')],
            [InlineKeyboardButton(text='👥 Join Group', url='https://t.me/')],
            [InlineKeyboardButton(text='📢 Join Channel', url='https://t.me/')],
            [InlineKeyboardButton(text='⬅ Back', callback_data='nav:main')],
        ]
    )


def seller_category_keyboard(categories: list[tuple[int, str]]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for category_id, label in categories:
        builder.button(text=label, callback_data=f'admin:addproduct:category:{category_id}')
    builder.adjust(2)
    return builder.as_markup()


def seller_subcategory_keyboard(subcategories: list[Subcategory], skip_label: str = 'No Subcategory') -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for sub in subcategories:
        builder.button(text=sub.label, callback_data=f'admin:addproduct:subcategory:{sub.id}')
    builder.button(text=skip_label, callback_data='admin:addproduct:subcategory:0')
    builder.adjust(2)
    return builder.as_markup()


def pending_product_keyboard(product_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text='✅ Approve', callback_data=f'admin:approve:{product_id}'),
                InlineKeyboardButton(text='❌ Reject', callback_data=f'admin:reject:{product_id}'),
            ]
        ]
    )

def super_admin_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text='Products'), KeyboardButton(text='Sellers')],
            [KeyboardButton(text='Orders'), KeyboardButton(text='Finance')],
            [KeyboardButton(text='Broadcast')],
            [KeyboardButton(text='Store Menu')],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def seller_admin_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text='Add Product'), KeyboardButton(text='My Products')],
            [KeyboardButton(text='My Sales'), KeyboardButton(text='Buyers')],
            [KeyboardButton(text='Store Menu')],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def sellers_manage_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text='➕ Add Seller', callback_data='seller:add')],
            [InlineKeyboardButton(text='📋 List Sellers', callback_data='seller:list')],
            [InlineKeyboardButton(text='➖ Remove Seller', callback_data='seller:remove')],
            [InlineKeyboardButton(text='⬅ Back', callback_data='admin:home')],
        ]
    )
def product_manage_keyboard(product_id: int, is_disabled: bool = False, is_super_admin: bool = False) -> InlineKeyboardMarkup:
    rows = []
    if is_disabled:
        rows.append([InlineKeyboardButton(text='✅ Enable', callback_data=f'admin:enable:{product_id}')])
    else:
        rows.append([InlineKeyboardButton(text='⛔ Disable', callback_data=f'admin:disable:{product_id}')])

    if is_super_admin:
        rows.append([InlineKeyboardButton(text='📦 Resend to Buyer', callback_data=f'admin:resend:{product_id}')])

    rows.append([InlineKeyboardButton(text='🗑 Soft Delete', callback_data=f'admin:delete:{product_id}')])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def referral_keyboard(bot_username: str, referral_code: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text='🔗 Share Referral Link', url=f'https://t.me/{bot_username}?start={referral_code}')],
            [InlineKeyboardButton(text='⬅ Back', callback_data='nav:main')],
        ]
    )
