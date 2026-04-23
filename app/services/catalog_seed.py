from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Category, CategoryKind, Subcategory


CATALOG = [
    {
        'name': 'tools',
        'label': 'Tools',
        'kind': CategoryKind.subcategory.value,
        'sort_order': 1,
        'subcategories': ['Stools', 'Bts', 'C and C', 'Btools', 'Gs and Bs'],
    },
    {
        'name': 'logs',
        'label': 'Logs',
        'kind': CategoryKind.subcategory.value,
        'sort_order': 2,
        'subcategories': ['Bwe', 'Tp-l', 'C-l', 'O-l', 'E-l', 'C and U checked'],
    },
    {
        'name': 'docs',
        'label': 'Docs',
        'kind': CategoryKind.direct_products.value,
        'sort_order': 3,
    },
    {
        'name': 'service',
        'label': 'Service',
        'kind': CategoryKind.message_only.value,
        'message_text': '*Services*\n\nRequest for a particular service with your specifics.\nContact admin.',
        'sort_order': 4,
    },
    {
        'name': 'tutorials',
        'label': 'Tutorials',
        'kind': CategoryKind.subcategory.value,
        'sort_order': 5,
        'subcategories': ['s-tutorials', 'btu tutorials', 'cd', 'tc', 'at', 'sp'],
    },
    {
        'name': 'support',
        'label': 'Support',
        'kind': CategoryKind.external_link.value,
        'external_url': 'https://t.me/jackal1441',
        'sort_order': 6,
    },
]


async def seed_catalog(session: AsyncSession) -> None:
    existing = await session.scalar(select(Category.id).limit(1))
    if existing:
        return

    for item in CATALOG:
        category = Category(
            name=item['name'],
            label=item['label'],
            kind=item['kind'],
            message_text=item.get('message_text'),
            external_url=item.get('external_url'),
            sort_order=item['sort_order'],
        )
        session.add(category)
        await session.flush()

        for idx, sub in enumerate(item.get('subcategories', []), start=1):
            session.add(
                Subcategory(
                    category_id=category.id,
                    name=sub.lower().replace(' ', '_'),
                    label=sub,
                    sort_order=idx,
                )
            )

    await session.commit()
