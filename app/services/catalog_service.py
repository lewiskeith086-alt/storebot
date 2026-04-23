from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Category, Product, ProductApprovalStatus, Subcategory


async def list_categories(session: AsyncSession):
    result = await session.scalars(select(Category).order_by(Category.sort_order.asc()))
    return list(result)


async def get_category_by_name(session: AsyncSession, name: str):
    return await session.scalar(select(Category).where(Category.name == name))


async def list_subcategories(session: AsyncSession, category_id: int):
    result = await session.scalars(
        select(Subcategory).where(Subcategory.category_id == category_id).order_by(Subcategory.sort_order.asc())
    )
    return list(result)


async def list_products_for_category(session: AsyncSession, category_id: int):
    result = await session.scalars(
        select(Product)
        .where(
            Product.category_id == category_id,
            Product.subcategory_id.is_(None),
            Product.is_active.is_(True),
            Product.is_disabled.is_(False),
            Product.approval_status == ProductApprovalStatus.approved.value,
        )
        .order_by(Product.id.desc())
    )
    return list(result)


async def list_products_for_subcategory(session: AsyncSession, subcategory_id: int):
    result = await session.scalars(
        select(Product)
        .where(
            Product.subcategory_id == subcategory_id,
            Product.is_active.is_(True),
            Product.is_disabled.is_(False),
            Product.approval_status == ProductApprovalStatus.approved.value,
        )
        .order_by(Product.id.desc())
    )
    return list(result)


async def get_product(session: AsyncSession, product_id: int):
    return await session.scalar(
        select(Product).where(
            Product.id == product_id,
            Product.is_active.is_(True),
            Product.is_disabled.is_(False),
            Product.approval_status == ProductApprovalStatus.approved.value,
        )
    )


async def search_products(session: AsyncSession, query: str):
    q = f"%{query.lower()}%"
    result = await session.scalars(
        select(Product).where(
            Product.is_active.is_(True),
            Product.is_disabled.is_(False),
            Product.approval_status == ProductApprovalStatus.approved.value,
            or_(Product.title.ilike(q), Product.description.ilike(q), Product.delivery_text.ilike(q)),
        )
    )
    return list(result)
