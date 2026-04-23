from aiogram import Bot
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DeliveryType, Product, Purchase, User


async def deliver_product(bot: Bot, session: AsyncSession, user: User, product: Product) -> None:
    message = '✅ Payment confirmed. Your purchase is below.\n\nUse *My Purchases* anytime to access it again.'
    await bot.send_message(user.telegram_id, message, parse_mode='Markdown')

    if product.delivery_type in (DeliveryType.text.value, DeliveryType.document_and_text.value) and product.delivery_text:
        await bot.send_message(user.telegram_id, product.delivery_text)

    if product.delivery_type in (DeliveryType.document.value, DeliveryType.document_and_text.value) and product.telegram_file_id:
        await bot.send_document(
            user.telegram_id,
            document=product.telegram_file_id,
            caption=product.title,
        )


async def redeliver_all_purchases(bot: Bot, session: AsyncSession, user: User) -> int:
    purchases = await session.scalars(
        select(Purchase).where(Purchase.user_id == user.id).order_by(Purchase.delivered_at.desc())
    )
    count = 0
    for purchase in purchases:
        product = await session.get(Product, purchase.product_id)
        if product is None:
            continue
        await deliver_product(bot, session, user, product)
        count += 1
    return count
