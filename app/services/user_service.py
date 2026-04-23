from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import Referral, User, UserRole, Wallet

settings = get_settings()


def make_referral_code(telegram_id: int) -> str:
    return f"ref_{telegram_id}"


async def get_or_create_user(session: AsyncSession, telegram_user) -> User:
    user = await session.scalar(select(User).where(User.telegram_id == telegram_user.id))
    expected_role = UserRole.super_admin.value if telegram_user.id in settings.superadmin_ids else None

    if user:
        user.username = telegram_user.username
        user.first_name = telegram_user.first_name
        if expected_role:
            user.is_admin = True
            user.role = expected_role
        if not user.referral_code:
            user.referral_code = make_referral_code(user.telegram_id)
        await session.commit()
        return user

    user = User(
        telegram_id=telegram_user.id,
        username=telegram_user.username,
        first_name=telegram_user.first_name,
        is_admin=telegram_user.id in settings.superadmin_ids,
        role=UserRole.super_admin.value if telegram_user.id in settings.superadmin_ids else UserRole.user.value,
        referral_code=make_referral_code(telegram_user.id),
    )
    session.add(user)
    await session.flush()
    session.add(Wallet(user_id=user.id))
    await session.commit()
    await session.refresh(user)
    return user


async def apply_referral_code(session: AsyncSession, new_user: User, referral_code: str) -> tuple[bool, str]:
    referral_code = (referral_code or "").strip()
    if not referral_code:
        return False, "Missing referral code."

    if new_user.referred_by_user_id:
        return False, "Referral already set."

    referrer = await session.scalar(
        select(User).where(User.referral_code == referral_code)
    )
    if not referrer:
        return False, "Referral code not found."

    if referrer.id == new_user.id:
        return False, "You cannot refer yourself."

    existing = await session.scalar(
        select(Referral).where(Referral.referred_user_id == new_user.id)
    )
    if existing:
        return False, "Referral already recorded."

    new_user.referred_by_user_id = referrer.id
    session.add(
        Referral(
            referrer_user_id=referrer.id,
            referred_user_id=new_user.id,
            referral_code=referral_code,
        )
    )
    await session.commit()
    return True, referrer.username or referrer.first_name or str(referrer.telegram_id)


async def get_referral_stats(session: AsyncSession, user: User) -> tuple[int, list[User]]:
    refs = list(
        await session.scalars(
            select(User).where(User.referred_by_user_id == user.id).order_by(User.created_at.desc())
        )
    )
    return len(refs), refs
