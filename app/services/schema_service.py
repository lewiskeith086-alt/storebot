from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine


async def ensure_phase1_admin_schema(engine: AsyncEngine) -> None:
    stmts = [
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(30) DEFAULT 'user'",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS added_by_admin_id INTEGER NULL",
        "ALTER TABLE products ADD COLUMN IF NOT EXISTS owner_user_id INTEGER NULL",
        "ALTER TABLE products ADD COLUMN IF NOT EXISTS approved_by_user_id INTEGER NULL",
        "ALTER TABLE products ADD COLUMN IF NOT EXISTS approval_status VARCHAR(30) DEFAULT 'approved'",
        "ALTER TABLE products ADD COLUMN IF NOT EXISTS rejection_reason TEXT NULL",
        "ALTER TABLE products ADD COLUMN IF NOT EXISTS is_disabled BOOLEAN DEFAULT FALSE",
        "ALTER TABLE products ADD COLUMN IF NOT EXISTS approved_at TIMESTAMPTZ NULL",
        "UPDATE users SET role = 'super_admin' WHERE is_admin = TRUE AND (role IS NULL OR role = 'user')",
        "UPDATE users SET role = 'user' WHERE role IS NULL",
        "UPDATE products SET approval_status = 'approved' WHERE approval_status IS NULL",
        "UPDATE products SET is_disabled = FALSE WHERE is_disabled IS NULL",
        "UPDATE products SET approved_at = NOW() WHERE approved_at IS NULL AND approval_status = 'approved'",
    ]

    async with engine.begin() as conn:
        for stmt in stmts:
            await conn.execute(text(stmt))
