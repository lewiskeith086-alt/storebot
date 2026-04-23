from decimal import Decimal, InvalidOperation
from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, LabeledPrice, Message, PreCheckoutQuery
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.keyboards import (
    crypto_asset_keyboard,
    invoice_keyboard,
    persistent_main_menu_keyboard,
    product_details_keyboard,
    product_list_keyboard,
    referral_keyboard,
    subcategory_keyboard,
    support_keyboard,
    wallet_home_keyboard,
)
from app.models import Order, OrderStatus, PaymentAsset, PaymentMethod, PaymentRequest, Product, Wallet
from app.services.catalog_service import (
    get_category_by_name,
    get_product,
    list_products_for_category,
    list_products_for_subcategory,
    list_subcategories,
    search_products,
)
from app.services.delivery_service import deliver_product, redeliver_all_purchases
from app.services.payment_service import (
    PaymentError,
    create_crypto_invoice,
    create_product_order,
    create_wallet_topup_order,
    refresh_crypto_status,
    spend_wallet_for_order,
)
from app.services.user_service import apply_referral_code, get_or_create_user, get_referral_stats
from app.states import SearchStates, TopUpStates
from app.utils.formatters import usd

router = Router()
settings = get_settings()


async def _send_main_menu(message: Message):
    await message.answer(
        'Welcome to the store.\nChoose a category from the menu below.',
        reply_markup=persistent_main_menu_keyboard(),
    )


async def _send_main_menu_from_callback(call: CallbackQuery):
    await call.message.answer('Main menu is below.', reply_markup=persistent_main_menu_keyboard())
    await call.answer()


@router.message(CommandStart())
async def start_handler(message: Message, session: AsyncSession, bot: Bot):
    user = await get_or_create_user(session, message.from_user)

    parts = (message.text or "").split(maxsplit=1)
    if len(parts) > 1:
        payload = parts[1].strip()
        if payload.startswith("ref_"):
            ok, info = await apply_referral_code(session, user, payload)
            if ok:
                await message.answer(f"🎉 Referral applied successfully. Referred by: {info}")
                if user.referred_by_user_id:
                    referrer = await session.get(type(user), user.referred_by_user_id)
                    if referrer:
                        try:
                            await bot.send_message(
                                referrer.telegram_id,
                                f"🎉 You referred a new user: {user.username or user.first_name or user.telegram_id}"
                            )
                        except Exception:
                            pass

    await _send_main_menu(message)


@router.callback_query(F.data == 'nav:main')
async def main_nav(call: CallbackQuery):
    await _send_main_menu_from_callback(call)


@router.message(F.text == 'Store Menu')
async def store_menu_handler(message: Message):
    await _send_main_menu(message)


@router.message(F.text == 'Tools')
async def tools_menu_handler(message: Message, session: AsyncSession):
    category = await get_category_by_name(session, 'tools')
    if not category:
        await message.answer('Tools category not found.')
        return
    subcategories = await list_subcategories(session, category.id)
    await message.answer(f'*{category.label}*', parse_mode='Markdown', reply_markup=subcategory_keyboard(subcategories))


@router.message(F.text == 'Logs')
async def logs_menu_handler(message: Message, session: AsyncSession):
    category = await get_category_by_name(session, 'logs')
    if not category:
        await message.answer('Logs category not found.')
        return
    subcategories = await list_subcategories(session, category.id)
    await message.answer(f'*{category.label}*', parse_mode='Markdown', reply_markup=subcategory_keyboard(subcategories))


@router.message(F.text == 'Docs')
async def docs_menu_handler(message: Message, session: AsyncSession):
    category = await get_category_by_name(session, 'docs')
    if not category:
        await message.answer('Docs category not found.')
        return
    products = await list_products_for_category(session, category.id)
    if not products:
        await message.answer(f'*{category.label}*\n\nNo products yet.', parse_mode='Markdown')
        return
    await message.answer(f'*{category.label}*', parse_mode='Markdown', reply_markup=product_list_keyboard(products))


@router.message(F.text == 'Service')
async def service_menu_handler(message: Message, session: AsyncSession):
    category = await get_category_by_name(session, 'service')
    if not category:
        await message.answer('Service category not found.')
        return
    text = category.message_text or '*Services*\n\nRequest for a particular service with your specifics.\nContact admin.'
    await message.answer(text, parse_mode='Markdown', reply_markup=support_keyboard())


@router.message(F.text == 'Tutorials')
async def tutorials_menu_handler(message: Message, session: AsyncSession):
    category = await get_category_by_name(session, 'tutorials')
    if not category:
        await message.answer('Tutorials category not found.')
        return
    subcategories = await list_subcategories(session, category.id)
    await message.answer(f'*{category.label}*', parse_mode='Markdown', reply_markup=subcategory_keyboard(subcategories))


@router.message(F.text == 'Support')
async def support_menu_handler(message: Message):
    await message.answer('Contact support below:', reply_markup=support_keyboard())


@router.message(F.text == 'Referral')
async def referral_menu_handler(message: Message, session: AsyncSession):
    user = await get_or_create_user(session, message.from_user)
    count, refs = await get_referral_stats(session, user)
    link = f"https://t.me/{settings.bot_username}?start={user.referral_code}"
    preview = "\n".join(
        f"- {(r.username or r.first_name or r.telegram_id)}" for r in refs[:10]
    ) if refs else "No referrals yet."

    await message.answer(
        f"*Referral*\n\n"
        f"Your code: `{user.referral_code}`\n"
        f"Your link: `{link}`\n\n"
        f"Total referrals: *{count}*\n\n"
        f"{preview}",
        parse_mode='Markdown',
        reply_markup=referral_keyboard(settings.bot_username, user.referral_code),
    )


@router.message(F.text == 'Wallet')
async def wallet_menu_handler(message: Message, session: AsyncSession):
    user = await get_or_create_user(session, message.from_user)
    wallet = await session.scalar(select(Wallet).where(Wallet.user_id == user.id))
    balance = wallet.balance if wallet else Decimal('0')
    await message.answer(
        f'*Wallet*\n\nCurrent balance: *{usd(balance)}*',
        parse_mode='Markdown',
        reply_markup=wallet_home_keyboard(),
    )


@router.message(F.text == 'My Purchases')
async def my_purchases_menu_handler(message: Message, session: AsyncSession, bot: Bot):
    user = await get_or_create_user(session, message.from_user)
    delivered = await redeliver_all_purchases(bot, session, user)
    if delivered == 0:
        await message.answer('No purchases yet.')
    else:
        await message.answer(f'Redelivered {delivered} item(s).')


@router.callback_query(F.data.startswith('subcategory:'))
async def subcategory_handler(call: CallbackQuery, session: AsyncSession):
    subcategory_id = int(call.data.split(':')[1])
    products = await list_products_for_subcategory(session, subcategory_id)
    if not products:
        await call.message.answer('No products in this section yet.')
    else:
        await call.message.answer('Choose a product:', reply_markup=product_list_keyboard(products))
    await call.answer()


@router.callback_query(F.data.startswith('product:'))
async def product_handler(call: CallbackQuery, session: AsyncSession):
    product_id = int(call.data.split(':')[1])
    product = await get_product(session, product_id)
    if not product:
        await call.answer('Product not found', show_alert=True)
        return

    text = f"*{product.title}*\n\n{product.description}\n\nPrice: *{usd(product.price_usd)}*"
    await call.message.answer(text, parse_mode='Markdown', reply_markup=product_details_keyboard(product.id))
    await call.answer()


@router.callback_query(F.data.startswith('buy:wallet:'))
async def buy_wallet_handler(call: CallbackQuery, session: AsyncSession, bot: Bot):
    product_id = int(call.data.split(':')[2])
    product = await get_product(session, product_id)
    user = await get_or_create_user(session, call.from_user)

    if not product:
        await call.answer('Product not found', show_alert=True)
        return

    order = await create_product_order(session, user, product, PaymentMethod.wallet.value)
    success = await spend_wallet_for_order(session, user, order)
    if not success:
        await call.answer('Insufficient balance', show_alert=True)
        return

    await deliver_product(bot, session, user, product)
    await call.answer('Paid with wallet')


@router.callback_query(F.data.startswith('buy:crypto:'))
async def buy_crypto_handler(call: CallbackQuery, session: AsyncSession):
    product_id = int(call.data.split(':')[2])
    product = await get_product(session, product_id)
    user = await get_or_create_user(session, call.from_user)

    if not product:
        await call.answer('Product not found', show_alert=True)
        return

    order = await create_product_order(session, user, product, PaymentMethod.crypto.value)
    await session.commit()
    await call.message.answer('Choose crypto asset:', reply_markup=crypto_asset_keyboard(order.id))
    await call.answer()


@router.callback_query(F.data.startswith('buy:stars:'))
async def buy_stars_handler(call: CallbackQuery, session: AsyncSession, bot: Bot):
    product_id = int(call.data.split(':')[2])
    product = await get_product(session, product_id)
    user = await get_or_create_user(session, call.from_user)

    if not product:
        await call.answer('Product not found', show_alert=True)
        return

    order = await create_product_order(session, user, product, PaymentMethod.stars.value)
    await session.commit()

    await bot.send_invoice(
        chat_id=call.from_user.id,
        title=product.title,
        description=product.description[:255],
        payload=f'order:{order.id}',
        currency='XTR',
        prices=[LabeledPrice(label=product.title, amount=int(Decimal(product.price_usd) * 100))],
        provider_token='',
    )
    await call.answer('Invoice sent')


@router.pre_checkout_query()
async def process_pre_checkout_query(pre_checkout_query: PreCheckoutQuery, bot: Bot):
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)


@router.message(F.successful_payment)
async def successful_payment_handler(message: Message, session: AsyncSession, bot: Bot):
    payload = message.successful_payment.invoice_payload
    if not payload.startswith('order:'):
        return

    order_id = int(payload.split(':')[1])
    order = await session.get(Order, order_id)
    if not order:
        return

    order.status = OrderStatus.paid.value
    await session.commit()

    user = await get_or_create_user(session, message.from_user)
    if order.product_id:
        product = await session.get(Product, order.product_id)
        if product:
            await deliver_product(bot, session, user, product)


@router.callback_query(F.data.startswith('asset:'))
async def choose_asset_handler(call: CallbackQuery, session: AsyncSession):
    _, order_id_str, asset_value = call.data.split(':', 2)
    order_id = int(order_id_str)
    order = await session.get(Order, order_id)
    user = await get_or_create_user(session, call.from_user)

    if not order:
        await call.answer('Order missing', show_alert=True)
        return

    product = await session.get(Product, order.product_id) if order.product_id else None
    title = product.title if product else f'Wallet Top-up #{order.id}'
    invoice = await create_crypto_invoice(session, user, order, PaymentAsset(asset_value), title)

    media_path = Path(invoice.payment_request.qr_path) if invoice.payment_request.qr_path else None
    if media_path and media_path.exists():
        await call.message.answer_photo(
            FSInputFile(media_path),
            caption=invoice.payment_text,
            parse_mode='Markdown',
            reply_markup=invoice_keyboard(invoice.payment_request.id),
        )
    else:
        await call.message.answer(
            invoice.payment_text,
            parse_mode='Markdown',
            reply_markup=invoice_keyboard(invoice.payment_request.id),
        )
    await call.answer()


@router.callback_query(F.data.startswith('invoice:refresh:'))
async def invoice_refresh_handler(call: CallbackQuery, session: AsyncSession, bot: Bot):
    payment_request_id = int(call.data.split(':')[2])

    try:
        payment_request = await refresh_crypto_status(session, payment_request_id)
    except PaymentError as exc:
        await call.answer(str(exc), show_alert=True)
        return

    if payment_request.status == OrderStatus.paid.value:
        order = await session.get(Order, payment_request.order_id)
        user = await get_or_create_user(session, call.from_user)

        if order and order.product_id:
            product = await session.get(Product, order.product_id)
            if product:
                await deliver_product(bot, session, user, product)
                await call.answer('Payment confirmed')
                return

        await call.answer('Top-up confirmed')
        return

    await call.answer(f'Status: {payment_request.status}')


@router.callback_query(F.data.startswith('invoice:cancel:'))
async def invoice_cancel_handler(call: CallbackQuery, session: AsyncSession):
    payment_request_id = int(call.data.split(':')[2])

    payment_request = await session.get(PaymentRequest, payment_request_id)
    if not payment_request:
        await call.answer('Invoice not found', show_alert=True)
        return

    if payment_request.status == OrderStatus.paid.value:
        await call.answer('This invoice is already paid.', show_alert=True)
        return

    payment_request.status = OrderStatus.cancelled.value

    if payment_request.order_id:
        order = await session.get(Order, payment_request.order_id)
        if order and order.status == OrderStatus.pending.value:
            order.status = OrderStatus.cancelled.value

    await session.commit()

    text = '❌ Invoice cancelled.\n\nYou can create a new payment invoice anytime.'
    try:
        if call.message.photo:
            await call.message.edit_caption(caption=text, reply_markup=None)
        else:
            await call.message.edit_text(text, reply_markup=None)
    except Exception:
        await call.message.answer(text)

    await call.answer('Invoice cancelled')


@router.callback_query(F.data == 'wallet:home')
async def wallet_home_handler(call: CallbackQuery, session: AsyncSession):
    user = await get_or_create_user(session, call.from_user)
    wallet = await session.scalar(select(Wallet).where(Wallet.user_id == user.id))
    balance = wallet.balance if wallet else Decimal('0')
    text = f'*Wallet*\n\nCurrent balance: *{usd(balance)}*'
    await call.message.answer(text, parse_mode='Markdown', reply_markup=wallet_home_keyboard())
    await call.answer()


@router.callback_query(F.data == 'wallet:add')
async def wallet_add_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(TopUpStates.waiting_for_amount)
    await call.message.answer('Send the top-up amount in USD, for example: 25')
    await call.answer()


@router.message(TopUpStates.waiting_for_amount)
async def wallet_add_amount(message: Message, state: FSMContext):
    try:
        amount = Decimal(message.text.strip())
        if amount <= 0:
            raise InvalidOperation
    except Exception:
        await message.answer('Send a valid positive number.')
        return

    await state.update_data(amount=str(amount))
    await state.set_state(TopUpStates.waiting_for_asset)
    await message.answer('Choose asset: BTC or USDT (TRON). Send exactly: BTC or USDT')


@router.message(TopUpStates.waiting_for_asset)
async def wallet_add_asset(message: Message, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    amount = Decimal(data['amount'])
    text = (message.text or '').strip().upper()

    if text not in {'BTC', 'USDT'}:
        await message.answer('Send either BTC or USDT')
        return

    user = await get_or_create_user(session, message.from_user)
    order = await create_wallet_topup_order(session, user, amount)
    await session.commit()

    asset = PaymentAsset.btc if text == 'BTC' else PaymentAsset.usdt_tron
    invoice = await create_crypto_invoice(session, user, order, asset, f'Wallet Top-up #{order.id}')

    media_path = Path(invoice.payment_request.qr_path) if invoice.payment_request.qr_path else None
    if media_path and media_path.exists():
        await message.answer_photo(
            FSInputFile(media_path),
            caption=invoice.payment_text,
            parse_mode='Markdown',
            reply_markup=invoice_keyboard(invoice.payment_request.id),
        )
    else:
        await message.answer(
            invoice.payment_text,
            parse_mode='Markdown',
            reply_markup=invoice_keyboard(invoice.payment_request.id),
        )

    await state.clear()


@router.callback_query(F.data == 'purchase:mine')
async def my_purchases_handler(call: CallbackQuery, session: AsyncSession, bot: Bot):
    user = await get_or_create_user(session, call.from_user)
    delivered = await redeliver_all_purchases(bot, session, user)
    if delivered == 0:
        await call.answer('No purchases yet', show_alert=True)
    else:
        await call.answer(f'Redelivered {delivered} item(s)')


@router.callback_query(F.data == 'search:start')
async def search_start_handler(call: CallbackQuery, state: FSMContext):
    await state.set_state(SearchStates.waiting_for_query)
    await call.message.answer('Send a product keyword to search.')
    await call.answer()


@router.message(SearchStates.waiting_for_query)
async def search_query_handler(message: Message, state: FSMContext, session: AsyncSession):
    products = await search_products(session, message.text.strip())
    await state.clear()

    if not products:
        await message.answer('No matching products found.')
        return

    await message.answer('Search results:', reply_markup=product_list_keyboard(products[:20]))
