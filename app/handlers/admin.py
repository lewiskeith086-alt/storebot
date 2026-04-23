from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.keyboards import (
    pending_product_keyboard,
    persistent_main_menu_keyboard,
    product_manage_keyboard,
    seller_admin_menu_keyboard,
    seller_category_keyboard,
    seller_subcategory_keyboard,
    sellers_manage_keyboard,
    super_admin_menu_keyboard,
)
from app.models import (
    Category,
    Order,
    OrderStatus,
    Product,
    ProductApprovalStatus,
    Purchase,
    Subcategory,
    User,
    UserRole,
)
from app.services.delivery_service import deliver_product
from app.services.user_service import get_or_create_user
from app.states import (
    AddSellerStates,
    BroadcastStates,
    RejectProductStates,
    RemoveSellerStates,
    ResendProductStates,
    SellerAddProductStates,
)

router = Router()
settings = get_settings()


async def _require_any_admin(message: Message, session: AsyncSession) -> User | None:
    user = await get_or_create_user(session, message.from_user)
    if user.role not in {UserRole.seller_admin.value, UserRole.super_admin.value}:
        await message.answer("Admin access only.")
        return None
    return user


async def _require_super_admin_message(message: Message, session: AsyncSession) -> User | None:
    user = await get_or_create_user(session, message.from_user)
    if user.role != UserRole.super_admin.value:
        await message.answer("Super admin only.")
        return None
    return user


async def _require_super_admin_call(call: CallbackQuery, session: AsyncSession) -> User | None:
    user = await get_or_create_user(session, call.from_user)
    if user.role != UserRole.super_admin.value:
        await call.answer("Super admin only.", show_alert=True)
        return None
    return user


async def _get_user_product_scope_user(session: AsyncSession, tg_user) -> User:
    return await get_or_create_user(session, tg_user)


async def send_admin_menu(message: Message, user: User):
    if user.role == UserRole.super_admin.value:
        await message.answer("Super Admin Panel", reply_markup=super_admin_menu_keyboard())
    elif user.role == UserRole.seller_admin.value:
        await message.answer("Seller Admin Panel", reply_markup=seller_admin_menu_keyboard())


async def notify_super_admins(bot: Bot, text: str):
    for admin_id in settings.superadmin_ids:
        try:
            await bot.send_message(admin_id, text)
        except Exception:
            pass


async def list_admin_categories(session: AsyncSession) -> list[tuple[int, str]]:
    result = await session.scalars(
        select(Category)
        .where(Category.name.in_(["tools", "logs", "docs", "tutorials"]))
        .order_by(Category.sort_order.asc())
    )
    return [(cat.id, cat.label) for cat in result]


async def _can_manage_product(session: AsyncSession, tg_user, product: Product) -> tuple[bool, User]:
    user = await get_or_create_user(session, tg_user)
    if user.role == UserRole.super_admin.value:
        return True, user
    if user.role == UserRole.seller_admin.value and product.owner_user_id == user.id:
        return True, user
    return False, user


@router.message(Command("admin"))
async def admin_panel(message: Message, session: AsyncSession):
    user = await get_or_create_user(session, message.from_user)

    if user.role == UserRole.super_admin.value:
        await message.answer("Super Admin Panel", reply_markup=super_admin_menu_keyboard())
    elif user.role == UserRole.seller_admin.value:
        await message.answer("Seller Admin Panel", reply_markup=seller_admin_menu_keyboard())
    else:
        await message.answer("You are not an admin.")




@router.message(Command("cancel"))
async def cancel_admin_state(message: Message, state: FSMContext):
    current = await state.get_state()
    if not current:
        await message.answer("Nothing to cancel.")
        return
    await state.clear()
    await message.answer("Cancelled.")

@router.message(F.text == "Store Menu")
async def store_menu_handler(message: Message):
    await message.answer("Store menu is below.", reply_markup=persistent_main_menu_keyboard())


@router.callback_query(F.data == "admin:home")
async def admin_home_callback(call: CallbackQuery, session: AsyncSession):
    user = await get_or_create_user(session, call.from_user)

    if user.role == UserRole.super_admin.value:
        await call.message.answer("Super Admin Panel", reply_markup=super_admin_menu_keyboard())
    elif user.role == UserRole.seller_admin.value:
        await call.message.answer("Seller Admin Panel", reply_markup=seller_admin_menu_keyboard())
    else:
        await call.message.answer("You are not an admin.")

    await call.answer()


@router.message(F.text == "Products")
async def super_products_menu(message: Message, session: AsyncSession):
    user = await _require_super_admin_message(message, session)
    if not user:
        return

    pending_count = await session.scalar(
        select(func.count()).select_from(Product).where(Product.approval_status == ProductApprovalStatus.pending.value)
    )
    approved_count = await session.scalar(
        select(func.count()).select_from(Product).where(
            Product.approval_status == ProductApprovalStatus.approved.value,
            Product.is_active.is_(True),
            Product.is_disabled.is_(False),
        )
    )
    disabled_count = await session.scalar(
        select(func.count()).select_from(Product).where(
            (Product.is_disabled.is_(True)) | (Product.is_active.is_(False))
        )
    )

    await message.answer(
        "*Products*\n\n"
        f"Pending approvals: `{pending_count}`\n"
        f"Approved products: `{approved_count}`\n"
        f"Disabled/Deleted products: `{disabled_count}`\n\n"
        "Pending items are shown first. Recent approved/disabled items are shown below with controls.",
        parse_mode="Markdown",
    )

    pending_products = await session.scalars(
        select(Product)
        .where(Product.approval_status == ProductApprovalStatus.pending.value)
        .order_by(Product.created_at.asc())
    )

    for product in pending_products:
        owner = await session.get(User, product.owner_user_id) if product.owner_user_id else None
        owner_label = f"@{owner.username}" if owner and owner.username else (owner.first_name if owner else "Unknown")
        await message.answer(
            f"Pending Product #{product.id}\n"
            f"Title: {product.title}\n"
            f"Price: {product.price_usd} USD\n"
            f"Seller: {owner_label}",
            reply_markup=pending_product_keyboard(product.id),
        )

    managed_products = await session.scalars(
        select(Product).where(Product.approval_status != ProductApprovalStatus.pending.value).order_by(Product.created_at.desc()).limit(15)
    )
    for product in managed_products:
        status_bits = []
        if product.approval_status:
            status_bits.append(product.approval_status)
        if product.is_disabled:
            status_bits.append("disabled")
        if not product.is_active:
            status_bits.append("deleted")
        status_text = ", ".join(status_bits) if status_bits else "active"
        await message.answer(
            f"Product #{product.id}\n"
            f"Title: {product.title}\n"
            f"Price: {product.price_usd} USD\n"
            f"Status: {status_text}",
            reply_markup=product_manage_keyboard(product.id, is_disabled=bool(product.is_disabled or not product.is_active), is_super_admin=True),
        )


@router.callback_query(F.data.startswith("admin:approve:"))
async def approve_product(call: CallbackQuery, session: AsyncSession, bot: Bot):
    super_admin = await _require_super_admin_call(call, session)
    if not super_admin:
        return

    product_id = int(call.data.split(":")[2])
    product = await session.get(Product, product_id)
    if not product:
        await call.answer("Product not found", show_alert=True)
        return

    product.approval_status = ProductApprovalStatus.approved.value
    product.approved_by_user_id = super_admin.id
    product.approved_at = datetime.now(timezone.utc)
    product.rejection_reason = None
    product.is_active = True
    product.is_disabled = False
    await session.commit()

    await call.message.edit_text(f"✅ Product #{product.id} approved and now visible in store.")

    if product.owner_user_id:
        owner = await session.get(User, product.owner_user_id)
        if owner:
            try:
                await bot.send_message(
                    owner.telegram_id,
                    f"✅ Your product {product.title} was approved and is now live in the store."
                )
            except Exception:
                pass

    await call.answer("Approved")


@router.callback_query(F.data.startswith("admin:reject:"))
async def reject_product_start(call: CallbackQuery, state: FSMContext, session: AsyncSession):
    super_admin = await _require_super_admin_call(call, session)
    if not super_admin:
        return

    product_id = int(call.data.split(":")[2])
    product = await session.get(Product, product_id)
    if not product:
        await call.answer("Product not found", show_alert=True)
        return

    await state.set_state(RejectProductStates.waiting_for_reason)
    await state.update_data(reject_product_id=product.id)

    await call.message.answer(
        f"Send rejection reason for product #{product.id} ({product.title}).\n\nOr send: -"
    )
    await call.answer()


@router.message(RejectProductStates.waiting_for_reason)
async def reject_product_finish(message: Message, state: FSMContext, session: AsyncSession, bot: Bot):
    super_admin = await _require_super_admin_message(message, session)
    if not super_admin:
        return

    data = await state.get_data()
    product_id = data.get("reject_product_id")
    if not product_id:
        await message.answer("Reject flow expired. Try again.")
        await state.clear()
        return

    product = await session.get(Product, product_id)
    if not product:
        await message.answer("Product not found.")
        await state.clear()
        return

    reason = (message.text or "").strip()
    if reason == "-":
        reason = "Rejected by super admin."

    product.approval_status = ProductApprovalStatus.rejected.value
    product.rejection_reason = reason
    product.approved_by_user_id = super_admin.id
    product.approved_at = datetime.now(timezone.utc)
    await session.commit()

    await message.answer(
        f"❌ Product #{product.id} rejected.\n\nReason: {reason}"
    )

    if product.owner_user_id:
        owner = await session.get(User, product.owner_user_id)
        if owner:
            try:
                await bot.send_message(
                    owner.telegram_id,
                    f"❌ Your product {product.title} was rejected.\n\nReason: {reason}"
                )
            except Exception:
                pass

    await state.clear()


@router.message(F.text == "My Products")
async def my_products(message: Message, session: AsyncSession):
    user = await _require_any_admin(message, session)
    if not user:
        return

    query = select(Product).order_by(Product.created_at.desc()).where(Product.owner_user_id == user.id)
    products = list(await session.scalars(query.limit(30)))
    if not products:
        await message.answer("No products yet.")
        return

    for product in products:
        flags = []
        if product.approval_status:
            flags.append(product.approval_status)
        if product.is_disabled:
            flags.append("disabled")
        if not product.is_active:
            flags.append("deleted")
        status = ", ".join(flags) if flags else "active"
        text = f"Product #{product.id}\nTitle: {product.title}\nPrice: {product.price_usd} USD\nStatus: {status}"
        if product.approval_status == ProductApprovalStatus.rejected.value and product.rejection_reason:
            text += f"\nReason: {product.rejection_reason}"
        await message.answer(
            text,
            reply_markup=product_manage_keyboard(product.id, is_disabled=bool(product.is_disabled or not product.is_active), is_super_admin=(user.role == UserRole.super_admin.value)),
        )


@router.callback_query(F.data.startswith("admin:disable:"))
async def disable_product(call: CallbackQuery, session: AsyncSession):
    product_id = int(call.data.split(":")[2])
    product = await session.get(Product, product_id)
    if not product:
        await call.answer("Product not found", show_alert=True)
        return

    allowed, _ = await _can_manage_product(session, call.from_user, product)
    if not allowed:
        await call.answer("Not allowed", show_alert=True)
        return

    product.is_disabled = True
    await session.commit()
    await call.message.edit_text(f"⛔ Product #{product.id} disabled.")
    await call.answer("Disabled")


@router.callback_query(F.data.startswith("admin:enable:"))
async def enable_product(call: CallbackQuery, session: AsyncSession):
    product_id = int(call.data.split(":")[2])
    product = await session.get(Product, product_id)
    if not product:
        await call.answer("Product not found", show_alert=True)
        return

    allowed, _ = await _can_manage_product(session, call.from_user, product)
    if not allowed:
        await call.answer("Not allowed", show_alert=True)
        return

    product.is_disabled = False
    if product.approval_status == ProductApprovalStatus.approved.value:
        product.is_active = True
    await session.commit()
    await call.message.edit_text(f"✅ Product #{product.id} enabled.")
    await call.answer("Enabled")


@router.callback_query(F.data.startswith("admin:delete:"))
async def soft_delete_product(call: CallbackQuery, session: AsyncSession):
    product_id = int(call.data.split(":")[2])
    product = await session.get(Product, product_id)
    if not product:
        await call.answer("Product not found", show_alert=True)
        return

    allowed, _ = await _can_manage_product(session, call.from_user, product)
    if not allowed:
        await call.answer("Not allowed", show_alert=True)
        return

    product.is_active = False
    product.is_disabled = True
    await session.commit()
    await call.message.edit_text(f"🗑 Product #{product.id} soft deleted.")
    await call.answer("Deleted")


@router.callback_query(F.data.startswith("admin:resend:"))
async def resend_product_start(call: CallbackQuery, state: FSMContext, session: AsyncSession):
    super_admin = await _require_super_admin_call(call, session)
    if not super_admin:
        return

    product_id = int(call.data.split(":")[2])
    product = await session.get(Product, product_id)
    if not product:
        await call.answer("Product not found", show_alert=True)
        return

    await state.set_state(ResendProductStates.waiting_for_buyer_identity)
    await state.update_data(resend_product_id=product.id)
    await call.message.answer(
        f"Send buyer @username or numeric Telegram ID to resend product #{product.id} ({product.title})."
    )
    await call.answer()


@router.message(ResendProductStates.waiting_for_buyer_identity)
async def resend_product_finish(message: Message, state: FSMContext, session: AsyncSession, bot: Bot):
    super_admin = await _require_super_admin_message(message, session)
    if not super_admin:
        return

    data = await state.get_data()
    product_id = data.get("resend_product_id")
    if not product_id:
        await message.answer("Resend flow expired. Try again.")
        await state.clear()
        return

    product = await session.get(Product, product_id)
    if not product:
        await message.answer("Product not found.")
        await state.clear()
        return

    raw = (message.text or "").strip()
    buyer = None
    if raw.startswith("@"):
        buyer = await session.scalar(select(User).where(User.username == raw[1:]))
    elif raw.isdigit():
        buyer = await session.scalar(select(User).where(User.telegram_id == int(raw)))

    if not buyer:
        await message.answer("Buyer not found. Ask them to start the bot first or send a valid Telegram ID.")
        return

    await deliver_product(bot, session, buyer, product)
    await message.answer(f"📦 Product #{product.id} resent to {('@' + buyer.username) if buyer.username else buyer.telegram_id}.")
    await state.clear()


@router.message(F.text == "My Sales")
async def my_sales(message: Message, session: AsyncSession):
    user = await _require_any_admin(message, session)
    if not user:
        return

    query = (
        select(func.count(Purchase.id), func.coalesce(func.sum(Order.amount_usd), 0))
        .join(Order, Order.id == Purchase.order_id)
        .join(Product, Product.id == Purchase.product_id)
        .where(Order.status == OrderStatus.paid.value)
    )

    if user.role != UserRole.super_admin.value:
        query = query.where(Product.owner_user_id == user.id)

    sales_count, revenue = (await session.execute(query)).one()
    await message.answer(f"Sales Summary\n\nPaid sales: {sales_count}\nRevenue: {revenue} USD")


@router.message(F.text == "Buyers")
async def buyers_summary(message: Message, session: AsyncSession):
    user = await _require_any_admin(message, session)
    if not user:
        return

    query = (
        select(User.username, User.first_name, func.count(Purchase.id).label("items"))
        .join(Order, Order.user_id == User.id)
        .join(Purchase, Purchase.order_id == Order.id)
        .join(Product, Product.id == Purchase.product_id)
        .group_by(User.id)
        .order_by(func.count(Purchase.id).desc())
    )

    if user.role != UserRole.super_admin.value:
        query = query.where(Product.owner_user_id == user.id)

    rows = (await session.execute(query.limit(10))).all()
    if not rows:
        await message.answer("No buyers yet.")
        return

    text = "Top Buyers\n\n" + "\n".join(
        f"- {(username or first_name or 'Unknown')}: {items} purchase(s)"
        for username, first_name, items in rows
    )
    await message.answer(text)


@router.message(F.text == "Orders")
async def super_orders(message: Message, session: AsyncSession):
    user = await _require_super_admin_message(message, session)
    if not user:
        return

    pending = await session.scalar(
        select(func.count()).select_from(Order).where(Order.status == OrderStatus.pending.value)
    )
    paid = await session.scalar(
        select(func.count()).select_from(Order).where(Order.status == OrderStatus.paid.value)
    )
    cancelled = await session.scalar(
        select(func.count()).select_from(Order).where(Order.status == OrderStatus.cancelled.value)
    )
    await message.answer(f"Orders\n\nPending: {pending}\nPaid: {paid}\nCancelled: {cancelled}")


@router.message(F.text == "Finance")
async def super_finance(message: Message, session: AsyncSession):
    user = await _require_super_admin_message(message, session)
    if not user:
        return

    paid_orders = await session.scalar(
        select(func.coalesce(func.sum(Order.amount_usd), 0)).where(Order.status == OrderStatus.paid.value)
    )
    await message.answer(f"Finance\n\nGross paid volume: {paid_orders} USD")


@router.message(F.text == "Broadcast")
async def super_broadcast(message: Message, state: FSMContext, session: AsyncSession):
    user = await _require_super_admin_message(message, session)
    if not user:
        return

    await state.clear()
    await state.set_state(BroadcastStates.waiting_for_message)
    await message.answer(
        "Send the broadcast message to send to all users.\n\n"
        "You can send plain text only in this patch.\n"
        "Send /cancel to stop."
    )


@router.message(BroadcastStates.waiting_for_message)
async def super_broadcast_send(message: Message, state: FSMContext, session: AsyncSession, bot: Bot):
    user = await _require_super_admin_message(message, session)
    if not user:
        return

    text = (message.text or "").strip()
    if not text:
        await message.answer("Send a valid text message.")
        return

    users = list(await session.scalars(select(User).where(User.is_active.is_(True)).order_by(User.id.asc())))
    sent = 0
    failed = 0

    for target in users:
        try:
            await bot.send_message(target.telegram_id, text)
            sent += 1
        except Exception:
            failed += 1

    await state.clear()
    await message.answer(f"Broadcast finished.\n\nSent: {sent}\nFailed: {failed}")


@router.message(F.text == "Sellers")
async def sellers_entry(message: Message, session: AsyncSession):
    user = await get_or_create_user(session, message.from_user)
    if user.role != UserRole.super_admin.value:
        await message.answer("Only super admin can manage sellers.")
        return

    await message.answer("Seller Management", reply_markup=sellers_manage_keyboard())


@router.callback_query(F.data == "seller:add")
async def seller_add_start(call: CallbackQuery, state: FSMContext, session: AsyncSession):
    user = await get_or_create_user(session, call.from_user)
    if user.role != UserRole.super_admin.value:
        await call.answer("Only super admin can do this.", show_alert=True)
        return

    await state.set_state(AddSellerStates.waiting_for_identity)
    await call.message.answer(
        "Send the seller username or chat ID.\n\nExamples:\n@jackal1441\n123456789"
    )
    await call.answer()


@router.message(AddSellerStates.waiting_for_identity)
async def seller_add_finish(message: Message, state: FSMContext, session: AsyncSession):
    raw = (message.text or "").strip()
    target_user = None

    if raw.startswith("@"):
        username = raw[1:]
        target_user = await session.scalar(select(User).where(User.username == username))
        if not target_user:
            await message.answer(
                "That username is not in the database yet.\nAsk the person to start the bot first, then try again."
            )
            await state.clear()
            return
    elif raw.isdigit():
        telegram_id = int(raw)
        target_user = await session.scalar(select(User).where(User.telegram_id == telegram_id))
        if not target_user:
            target_user = User(
                telegram_id=telegram_id,
                username=None,
                first_name="Seller",
                role=UserRole.seller_admin.value,
                is_admin=True,
            )
            session.add(target_user)
            await session.commit()
            await message.answer(f"Seller added by chat ID: {telegram_id}")
            await state.clear()
            return
    else:
        await message.answer("Send a valid @username or numeric chat ID.")
        return

    target_user.role = UserRole.seller_admin.value
    target_user.is_admin = True
    await session.commit()

    label = f"@{target_user.username}" if target_user.username else str(target_user.telegram_id)
    await message.answer(f"Seller added: {label}")
    await state.clear()


@router.callback_query(F.data == "seller:list")
async def seller_list_handler(call: CallbackQuery, session: AsyncSession):
    rows = await session.scalars(
        select(User)
        .where(User.role.in_([UserRole.seller_admin.value, UserRole.super_admin.value]))
        .order_by(User.id.asc())
    )
    users = rows.all()

    if not users:
        await call.message.answer("No sellers/admins found.")
        await call.answer()
        return

    lines = ["Sellers / Admins", ""]
    for user in users:
        identity = f"@{user.username}" if user.username else f"ID: {user.telegram_id}"
        lines.append(f"{identity} - {user.role}")

    await call.message.answer("\n".join(lines))
    await call.answer()


@router.callback_query(F.data == "seller:remove")
async def seller_remove_start(call: CallbackQuery, state: FSMContext, session: AsyncSession):
    user = await get_or_create_user(session, call.from_user)
    if user.role != UserRole.super_admin.value:
        await call.answer("Only super admin can do this.", show_alert=True)
        return

    await state.set_state(RemoveSellerStates.waiting_for_identity)
    await call.message.answer(
        "Send the seller username or chat ID to remove seller access.\n\nExamples:\n@jackal1441\n123456789"
    )
    await call.answer()


@router.message(RemoveSellerStates.waiting_for_identity)
async def seller_remove_finish(message: Message, state: FSMContext, session: AsyncSession):
    raw = (message.text or "").strip()
    target_user = None

    if raw.startswith("@"):
        username = raw[1:]
        target_user = await session.scalar(select(User).where(User.username == username))
    elif raw.isdigit():
        telegram_id = int(raw)
        target_user = await session.scalar(select(User).where(User.telegram_id == telegram_id))
    else:
        await message.answer("Send a valid @username or numeric chat ID.")
        return

    if not target_user:
        await message.answer("User not found.")
        await state.clear()
        return

    if target_user.role == UserRole.super_admin.value:
        await message.answer("You cannot remove super admin access this way.")
        await state.clear()
        return

    target_user.role = UserRole.user.value
    target_user.is_admin = False
    await session.commit()

    label = f"@{target_user.username}" if target_user.username else str(target_user.telegram_id)
    await message.answer(f"Seller access removed: {label}")
    await state.clear()


@router.message(F.text == "Add Product")
async def seller_add_product_start(message: Message, state: FSMContext, session: AsyncSession):
    user = await _require_any_admin(message, session)
    if not user:
        return

    categories = await list_admin_categories(session)
    await state.clear()
    await state.set_state(SellerAddProductStates.waiting_for_category)
    await state.update_data(
        auto_approve=(user.role == UserRole.super_admin.value),
        owner_user_id=user.id,
    )
    await message.answer(
        "Choose a category for this product:",
        reply_markup=seller_category_keyboard(categories),
    )


@router.callback_query(
    SellerAddProductStates.waiting_for_category,
    F.data.startswith("admin:addproduct:category:")
)
async def seller_pick_category(call: CallbackQuery, state: FSMContext, session: AsyncSession):
    category_id = int(call.data.split(":")[-1])

    category = await session.get(Category, category_id)
    if not category:
        await call.answer("Category not found.", show_alert=True)
        return

    await state.update_data(category_id=category.id, category_name=category.name)

    if category.name == "docs":
        await state.update_data(subcategory_id=None)
        await state.set_state(SellerAddProductStates.waiting_for_title)
        await call.message.answer("Docs selected.\n\nNow send product title.")
        await call.answer()
        return

    subcategories = await session.scalars(
        select(Subcategory)
        .where(Subcategory.category_id == category.id)
        .order_by(Subcategory.sort_order.asc())
    )
    subs = list(subcategories)

    if not subs:
        await state.update_data(subcategory_id=None)
        await state.set_state(SellerAddProductStates.waiting_for_title)
        await call.message.answer(f"{category.label} selected.\n\nNow send product title.")
        await call.answer()
        return

    await state.set_state(SellerAddProductStates.waiting_for_subcategory)
    await call.message.answer(
        f"{category.label} selected.\n\nChoose a subcategory:",
        reply_markup=seller_subcategory_keyboard(subs),
    )
    await call.answer()


@router.callback_query(
    SellerAddProductStates.waiting_for_subcategory,
    F.data.startswith("admin:addproduct:subcategory:")
)
async def seller_pick_subcategory(call: CallbackQuery, state: FSMContext, session: AsyncSession):
    subcategory_id = int(call.data.split(":")[-1])

    if subcategory_id == 0:
        await state.update_data(subcategory_id=None)
        await state.set_state(SellerAddProductStates.waiting_for_title)
        await call.message.answer("No subcategory selected.\n\nNow send product title.")
        await call.answer()
        return

    subcategory = await session.get(Subcategory, subcategory_id)
    if not subcategory:
        await call.answer("Subcategory not found.", show_alert=True)
        return

    await state.update_data(subcategory_id=subcategory.id)
    await state.set_state(SellerAddProductStates.waiting_for_title)
    await call.message.answer(f"{subcategory.label} selected.\n\nNow send product title.")
    await call.answer()


@router.message(SellerAddProductStates.waiting_for_title)
async def seller_add_product_title(message: Message, state: FSMContext):
    title = (message.text or "").strip()
    if not title:
        await message.answer("Send a valid title.")
        return

    await state.update_data(title=title)
    await state.set_state(SellerAddProductStates.waiting_for_description)
    await message.answer("Send product description.")


@router.message(SellerAddProductStates.waiting_for_description)
async def seller_add_product_description(message: Message, state: FSMContext):
    description = (message.text or "").strip()
    if not description:
        await message.answer("Send a valid description.")
        return

    await state.update_data(description=description)
    await state.set_state(SellerAddProductStates.waiting_for_price)
    await message.answer("Send product price in USD, for example: 25")


@router.message(SellerAddProductStates.waiting_for_price)
async def seller_add_product_price(message: Message, state: FSMContext):
    raw = (message.text or "").strip()

    try:
        price = Decimal(raw)
        if price <= 0:
            raise InvalidOperation
    except Exception:
        await message.answer("Send a valid positive price, for example: 25")
        return

    await state.update_data(price=str(price))
    await state.set_state(SellerAddProductStates.waiting_for_file)
    await message.answer("Now send the product file as a Telegram document.")


@router.message(SellerAddProductStates.waiting_for_file, F.document)
async def seller_add_product_file(message: Message, state: FSMContext):
    document = message.document

    await state.update_data(
        file_id=document.file_id,
        file_name=document.file_name or "product_file",
    )
    await state.set_state(SellerAddProductStates.waiting_for_delivery_text)
    await message.answer("Send extra delivery text or instructions for the buyer. Send '-' if none.")


@router.message(SellerAddProductStates.waiting_for_file)
async def seller_add_product_file_invalid(message: Message):
    await message.answer("Please send the product as a Telegram document/file.")


@router.message(SellerAddProductStates.waiting_for_delivery_text)
async def seller_add_product_finish(message: Message, state: FSMContext, session: AsyncSession, bot: Bot):
    user = await get_or_create_user(session, message.from_user)
    data = await state.get_data()

    delivery_text = (message.text or "").strip()
    if delivery_text == "-":
        delivery_text = None

    approval_status = (
        ProductApprovalStatus.approved.value
        if user.role == UserRole.super_admin.value
        else ProductApprovalStatus.pending.value
    )

    product = Product(
        title=data["title"],
        description=data["description"],
        price_usd=Decimal(data["price"]),
        category_id=data["category_id"],
        subcategory_id=data.get("subcategory_id"),
        telegram_file_id=data["file_id"],
        delivery_text=delivery_text,
        is_active=True,
        is_disabled=False,
        owner_user_id=user.id,
        approval_status=approval_status,
        approved_by_user_id=user.id if user.role == UserRole.super_admin.value else None,
        approved_at=datetime.now(timezone.utc) if user.role == UserRole.super_admin.value else None,
        rejection_reason=None,
    )

    session.add(product)
    await session.commit()
    await session.refresh(product)

    if user.role == UserRole.super_admin.value:
        await message.answer(
            f"Product created and approved.\n\n"
            f"ID: {product.id}\n"
            f"Title: {product.title}\n"
            f"Price: ${product.price_usd}"
        )
    else:
        await message.answer(
            f"Product submitted for approval.\n\n"
            f"ID: {product.id}\n"
            f"Title: {product.title}\n"
            f"Price: ${product.price_usd}"
        )
        await notify_super_admins(
            bot,
            f"New seller product pending approval\n\n"
            f"Title: {product.title}\n"
            f"Price: {product.price_usd} USD\n"
            f"Product ID: {product.id}"
        )

    await state.clear()


@router.message(F.text == "Add New Product")
async def add_new_product_alias(message: Message, state: FSMContext, session: AsyncSession):
    await seller_add_product_start(message, state, session)


@router.message(F.text == "View Users")
async def view_users_alias(message: Message, session: AsyncSession):
    user = await _require_super_admin_message(message, session)
    if not user:
        return

    total = await session.scalar(select(func.count()).select_from(User))
    sellers = await session.scalar(
        select(func.count()).select_from(User).where(User.role == UserRole.seller_admin.value)
    )
    supers = await session.scalar(
        select(func.count()).select_from(User).where(User.role == UserRole.super_admin.value)
    )

    await message.answer(
        f"Users\n\nTotal: {total}\nSellers: {sellers}\nSuper Admins: {supers}"
    )
