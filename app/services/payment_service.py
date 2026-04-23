from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_DOWN
from pathlib import Path
from urllib.parse import quote

import httpx
import qrcode
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import (
    Order,
    OrderStatus,
    PaymentAsset,
    PaymentMethod,
    PaymentRequest,
    Product,
    Purchase,
    User,
    Wallet,
    WalletTransaction,
    WalletTransactionType,
)

settings = get_settings()
QR_DIR = Path('runtime/qr')
QR_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class InvoicePreview:
    payment_request: PaymentRequest
    title: str
    payment_text: str


class PaymentError(Exception):
    pass


def _quantize_amount(value: Decimal, precision: str) -> Decimal:
    return value.quantize(Decimal(precision), rounding=ROUND_DOWN)


def _make_unique_amount(base_amount: Decimal, user_id: int, product_id: int | None = None, precision: str = '0.00000001') -> Decimal:
    suffix_seed = (user_id % 97) + ((product_id or 0) % 89)
    suffix = Decimal(suffix_seed) / Decimal('100000')
    return _quantize_amount(base_amount + suffix, precision)


async def create_wallet_topup_order(session: AsyncSession, user: User, amount_usd: Decimal) -> Order:
    order = Order(user_id=user.id, product_id=None, amount_usd=amount_usd, payment_method=PaymentMethod.crypto.value)
    session.add(order)
    await session.flush()
    return order


async def create_product_order(session: AsyncSession, user: User, product: Product, method: str) -> Order:
    order = Order(user_id=user.id, product_id=product.id, amount_usd=product.price_usd, payment_method=method)
    session.add(order)
    await session.flush()
    return order


async def create_crypto_invoice(
    session: AsyncSession,
    user: User,
    order: Order,
    asset: PaymentAsset,
    title: str,
) -> InvoicePreview:
    if asset == PaymentAsset.usdt_tron:
        expected = _make_unique_amount(Decimal(order.amount_usd), user.id, order.product_id, '0.000001')
        address = settings.tron_receive_address
        network = 'TRON'
        qr_payload = f"tron:{address}?token={settings.usdt_trc20_contract}&amount={expected}"
    else:
        # Placeholder conversion rate: for production, replace this with a live BTC/USD price source.
        btc_price_usd = Decimal('85000')
        btc_amount = Decimal(order.amount_usd) / btc_price_usd
        expected = _make_unique_amount(btc_amount, user.id, order.product_id, '0.00000001')
        address = settings.btc_receive_address
        network = 'BITCOIN'
        qr_payload = f"bitcoin:{address}?amount={expected}&label={quote(title)}"

    payment_request = PaymentRequest(
        user_id=user.id,
        order_id=order.id,
        kind='product_purchase' if order.product_id else 'wallet_topup',
        method=PaymentMethod.crypto.value,
        asset=asset.value,
        network=network,
        receiving_address=address,
        expected_amount=expected,
        unique_amount=expected,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=settings.invoice_expiry_minutes),
    )
    session.add(payment_request)
    await session.flush()

    qr_path = QR_DIR / f"payment_{payment_request.id}.png"
    qrcode.make(qr_payload).save(qr_path)
    payment_request.qr_path = str(qr_path)
    await session.commit()
    await session.refresh(payment_request)

    text = (
        f"*{title}*\n\n"
        f"Send exactly: `{payment_request.expected_amount}` {asset.value.replace('_TRC20', '')}\n"
        f"Network: `{payment_request.network}`\n"
        f"Address: `{payment_request.receiving_address}`\n"
        f"Expires: `{payment_request.expires_at.strftime('%Y-%m-%d %H:%M UTC')}`\n\n"
        "After payment, tap *Refresh Status*."
    )
    return InvoicePreview(payment_request=payment_request, title=title, payment_text=text)


async def spend_wallet_for_order(session: AsyncSession, user: User, order: Order) -> bool:
    wallet = await session.scalar(select(Wallet).where(Wallet.user_id == user.id))
    if not wallet or wallet.balance < order.amount_usd:
        return False

    wallet.balance -= order.amount_usd
    order.status = OrderStatus.paid.value
    session.add(
        WalletTransaction(
            wallet_id=wallet.id,
            tx_type=WalletTransactionType.debit.value,
            amount=order.amount_usd,
            source='product_purchase',
            reference=f'order:{order.id}',
        )
    )
    await session.commit()
    return True


async def credit_wallet(session: AsyncSession, user_id: int, amount: Decimal, source: str, reference: str) -> None:
    wallet = await session.scalar(select(Wallet).where(Wallet.user_id == user_id))
    if wallet is None:
        raise PaymentError('Wallet missing for user')
    wallet.balance += amount
    session.add(
        WalletTransaction(
            wallet_id=wallet.id,
            tx_type=WalletTransactionType.credit.value,
            amount=amount,
            source=source,
            reference=reference,
        )
    )
    await session.commit()


async def mark_order_paid_and_deliver(session: AsyncSession, payment_request_id: int) -> tuple[Order, Product | None]:
    payment_request = await session.get(PaymentRequest, payment_request_id)
    if not payment_request:
        raise PaymentError('Payment request not found')
    order = await session.get(Order, payment_request.order_id)
    if not order:
        raise PaymentError('Order not found')

    if order.status == OrderStatus.paid.value:
        product = await session.get(Product, order.product_id) if order.product_id else None
        return order, product

    order.status = OrderStatus.paid.value
    payment_request.status = OrderStatus.paid.value
    payment_request.paid_at = datetime.now(timezone.utc)

    product = await session.get(Product, order.product_id) if order.product_id else None
    if product is None:
        await credit_wallet(session, payment_request.user_id, order.amount_usd, 'crypto_topup', f'payment_request:{payment_request.id}')
    else:
        session.add(Purchase(user_id=payment_request.user_id, product_id=product.id, order_id=order.id))
        await session.commit()

    return order, product


async def refresh_crypto_status(session: AsyncSession, payment_request_id: int) -> PaymentRequest:
    payment_request = await session.get(PaymentRequest, payment_request_id)
    if not payment_request:
        raise PaymentError('Payment request not found')
    if payment_request.status == OrderStatus.paid.value:
        return payment_request
    if payment_request.expires_at < datetime.now(timezone.utc):
        payment_request.status = OrderStatus.expired.value
        if payment_request.order_id:
            order = await session.get(Order, payment_request.order_id)
            if order:
                order.status = OrderStatus.expired.value
        await session.commit()
        return payment_request

    if payment_request.asset == PaymentAsset.btc.value:
        paid, tx_hash, confirmations = await check_btc_invoice(payment_request)
    else:
        paid, tx_hash, confirmations = await check_tron_invoice(payment_request)

    payment_request.tx_hash = tx_hash
    payment_request.confirmations = confirmations
    if paid:
        await mark_order_paid_and_deliver(session, payment_request.id)
        payment_request = await session.get(PaymentRequest, payment_request.id)
    else:
        await session.commit()
    return payment_request


async def check_btc_invoice(payment_request: PaymentRequest) -> tuple[bool, str | None, int]:
    base_url = settings.memppool_base_url.rstrip('/')
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(f"{base_url}/api/address/{payment_request.receiving_address}/txs")
        response.raise_for_status()
        txs = response.json()

        for tx in txs:
            received = Decimal('0')
            for vout in tx.get('vout', []):
                if vout.get('scriptpubkey_address') == payment_request.receiving_address:
                    received += Decimal(vout.get('value', 0)) / Decimal('100000000')
            if received == Decimal(payment_request.expected_amount):
                status = tx.get('status', {})
                confirmations = 1 if status.get('confirmed') else 0
                paid = confirmations >= settings.btc_confirmations_required
                return paid, tx.get('txid'), confirmations
    return False, None, 0


async def check_tron_invoice(payment_request: PaymentRequest) -> tuple[bool, str | None, int]:
    headers = {'accept': 'application/json'}
    if settings.trongrid_api_key:
        headers['TRON-PRO-API-KEY'] = settings.trongrid_api_key

    url = (
        f"{settings.trongrid_base_url.rstrip('/')}/v1/accounts/{payment_request.receiving_address}/transactions/trc20"
        f"?contract_address={settings.usdt_trc20_contract}&limit=50&only_to=true"
    )
    async with httpx.AsyncClient(timeout=15, headers=headers) as client:
        response = await client.get(url)
        response.raise_for_status()
        payload = response.json()
        for tx in payload.get('data', []):
            to_addr = tx.get('to')
            if to_addr != payment_request.receiving_address:
                continue
            raw_value = Decimal(tx.get('value', '0')) / Decimal('1000000')
            if raw_value == Decimal(payment_request.expected_amount):
                confirmations = int(tx.get('block_timestamp') is not None)
                paid = confirmations >= settings.tron_confirmations_required
                return paid, tx.get('transaction_id'), confirmations
    return False, None, 0
