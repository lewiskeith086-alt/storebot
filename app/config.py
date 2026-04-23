from functools import lru_cache
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    bot_token: str = Field(alias='BOT_TOKEN')
    bot_username: str = Field(alias='BOT_USERNAME')
    public_base_url: str = Field(alias='PUBLIC_BASE_URL')
    webhook_secret: str = Field(alias='WEBHOOK_SECRET')
    superadmin_ids_raw: str = Field(alias='SUPERADMIN_IDS')
    database_url: str = Field(alias='DATABASE_URL')
    support_username: str = Field(default='jackal1441', alias='SUPPORT_USERNAME')

    btc_receive_address: str = Field(alias='BTC_RECEIVE_ADDRESS')
    tron_receive_address: str = Field(alias='TRON_RECEIVE_ADDRESS')
    trongrid_api_key: str | None = Field(default=None, alias='TRONGRID_API_KEY')
    usdt_trc20_contract: str = Field(alias='USDT_TRC20_CONTRACT')

    btc_confirmations_required: int = Field(default=1, alias='BTC_CONFIRMATIONS_REQUIRED')
    tron_confirmations_required: int = Field(default=1, alias='TRON_CONFIRMATIONS_REQUIRED')
    stars_enabled: bool = Field(default=True, alias='STARS_ENABLED')
    store_currency: str = Field(default='USD', alias='STORE_CURRENCY')
    invoice_expiry_minutes: int = Field(default=30, alias='INVOICE_EXPIRY_MINUTES')
    memppool_base_url: str = Field(default='https://mempool.space', alias='MEMPPOOL_BASE_URL')
    trongrid_base_url: str = Field(default='https://api.trongrid.io', alias='TRONGRID_BASE_URL')

    @property
    def superadmin_ids(self) -> List[int]:
        return [int(item.strip()) for item in self.superadmin_ids_raw.split(',') if item.strip()]

    @property
    def webhook_url(self) -> str:
        return f"{self.public_base_url.rstrip('/')}/telegram/webhook/{self.webhook_secret}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
