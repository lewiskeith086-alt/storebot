from contextlib import asynccontextmanager
import traceback

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import Update
from fastapi import Depends, FastAPI, HTTPException, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import Base, SessionLocal, engine, get_db_session
from app.handlers.admin import router as admin_router
from app.handlers.user import router as user_router
from app.services.catalog_seed import seed_catalog

settings = get_settings()
bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN))
dp = Dispatcher()
dp.include_router(admin_router)
dp.include_router(user_router)


@asynccontextmanager
async def lifespan(_: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        await conn.execute(text("ALTER TABLE products ADD COLUMN IF NOT EXISTS owner_user_id INTEGER NULL"))
        await conn.execute(text("ALTER TABLE products ADD COLUMN IF NOT EXISTS approval_status VARCHAR(20) NOT NULL DEFAULT 'approved'"))
        await conn.execute(text("ALTER TABLE products ADD COLUMN IF NOT EXISTS approved_by_user_id INTEGER NULL"))
        await conn.execute(text("ALTER TABLE products ADD COLUMN IF NOT EXISTS rejection_reason TEXT NULL"))
        await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS referred_by_user_id INTEGER NULL"))
        await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS referral_code VARCHAR(64) NULL"))

    async with SessionLocal() as session:
        await seed_catalog(session)

    await bot.set_webhook(settings.webhook_url, secret_token=settings.webhook_secret)
    yield
    await bot.delete_webhook(drop_pending_updates=False)
    await bot.session.close()


app = FastAPI(lifespan=lifespan)


@app.get('/')
async def root():
    return {'ok': True, 'service': 'telegram-digital-store-bot'}


@app.post('/telegram/webhook/{secret}')
async def telegram_webhook(secret: str, request: Request):
    if secret != settings.webhook_secret:
        raise HTTPException(status_code=404, detail='Not found')

    try:
        payload = await request.json()
        print('INCOMING UPDATE:', payload)

        update = Update.model_validate(payload, context={'bot': bot})

        async with SessionLocal() as session:
            result = await dp.feed_update(bot, update, session=session)
            print('DISPATCH RESULT:', result)

        return {'ok': True}

    except Exception as e:
        print('WEBHOOK ERROR:')
        traceback.print_exc()
        return {'ok': False, 'error': str(e)}


@app.get('/healthz')
async def healthz(session: AsyncSession = Depends(get_db_session)):
    await session.execute(text('SELECT 1'))
    return {'ok': True}