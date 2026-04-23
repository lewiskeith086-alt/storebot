from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class CategoryKind(str, Enum):
    subcategory = 'subcategory'
    direct_products = 'direct_products'
    message_only = 'message_only'
    external_link = 'external_link'


class PaymentMethod(str, Enum):
    wallet = 'wallet'
    crypto = 'crypto'
    stars = 'stars'


class PaymentAsset(str, Enum):
    btc = 'BTC'
    usdt_tron = 'USDT_TRC20'


class OrderStatus(str, Enum):
    pending = 'pending'
    paid = 'paid'
    expired = 'expired'
    cancelled = 'cancelled'
    underpaid = 'underpaid'
    overpaid = 'overpaid'


class WalletTransactionType(str, Enum):
    credit = 'credit'
    debit = 'debit'
    refund = 'refund'
    adjustment = 'adjustment'


class DeliveryType(str, Enum):
    document = 'document'
    text = 'text'
    document_and_text = 'document_and_text'


class UserRole(str, Enum):
    user = 'user'
    seller_admin = 'seller_admin'
    super_admin = 'super_admin'


class ProductApprovalStatus(str, Enum):
    pending = 'pending'
    approved = 'approved'
    rejected = 'rejected'


class User(Base):
    __tablename__ = 'users'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    role: Mapped[str] = mapped_column(String(30), default=UserRole.user.value)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    added_by_admin_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    referred_by_user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    referral_code: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    wallet: Mapped['Wallet'] = relationship(back_populates='user', uselist=False, cascade='all, delete-orphan')
    orders: Mapped[list['Order']] = relationship(back_populates='user')
    purchases: Mapped[list['Purchase']] = relationship(back_populates='user')
    products_owned: Mapped[list['Product']] = relationship(
        back_populates='owner', foreign_keys='Product.owner_user_id'
    )
    referrals_sent: Mapped[list['Referral']] = relationship(
        back_populates='referrer', foreign_keys='Referral.referrer_user_id'
    )
    referral_record: Mapped['Referral | None'] = relationship(
        back_populates='referred_user', foreign_keys='Referral.referred_user_id', uselist=False
    )

    @property
    def is_super_admin(self) -> bool:
        return self.role == UserRole.super_admin.value

    @property
    def is_seller_admin(self) -> bool:
        return self.role == UserRole.seller_admin.value



class Referral(Base):
    __tablename__ = 'referrals'
    __table_args__ = (UniqueConstraint('referred_user_id', name='uq_referrals_referred_user'),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    referrer_user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    referred_user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    referral_code: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    referrer: Mapped[User] = relationship(foreign_keys=[referrer_user_id], back_populates='referrals_sent')
    referred_user: Mapped[User] = relationship(foreign_keys=[referred_user_id], back_populates='referral_record')


class Wallet(Base):
    __tablename__ = 'wallets'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), unique=True)
    balance: Mapped[Decimal] = mapped_column(Numeric(18, 8), default=Decimal('0'))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user: Mapped[User] = relationship(back_populates='wallet')
    transactions: Mapped[list['WalletTransaction']] = relationship(back_populates='wallet', cascade='all, delete-orphan')


class WalletTransaction(Base):
    __tablename__ = 'wallet_transactions'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    wallet_id: Mapped[int] = mapped_column(ForeignKey('wallets.id'))
    tx_type: Mapped[str] = mapped_column(String(30))
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 8))
    source: Mapped[str] = mapped_column(String(50))
    reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    wallet: Mapped[Wallet] = relationship(back_populates='transactions')


class Category(Base):
    __tablename__ = 'categories'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    label: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(30))
    message_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    external_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    subcategories: Mapped[list['Subcategory']] = relationship(back_populates='category', cascade='all, delete-orphan')
    products: Mapped[list['Product']] = relationship(back_populates='category')


class Subcategory(Base):
    __tablename__ = 'subcategories'
    __table_args__ = (UniqueConstraint('category_id', 'name', name='uq_category_subcategory_name'),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey('categories.id'))
    name: Mapped[str] = mapped_column(String(120))
    label: Mapped[str] = mapped_column(String(120))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    category: Mapped[Category] = relationship(back_populates='subcategories')
    products: Mapped[list['Product']] = relationship(back_populates='subcategory')


class Product(Base):
    __tablename__ = 'products'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey('categories.id'))
    subcategory_id: Mapped[int | None] = mapped_column(ForeignKey('subcategories.id'), nullable=True)
    owner_user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    approved_by_user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)
    price_usd: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    delivery_type: Mapped[str] = mapped_column(String(30), default=DeliveryType.document_and_text.value)
    telegram_file_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    delivery_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    approval_status: Mapped[str] = mapped_column(String(30), default=ProductApprovalStatus.approved.value)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_disabled: Mapped[bool] = mapped_column(Boolean, default=False)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    category: Mapped[Category] = relationship(back_populates='products')
    subcategory: Mapped[Subcategory | None] = relationship(back_populates='products')
    owner: Mapped[User | None] = relationship(back_populates='products_owned', foreign_keys=[owner_user_id])
    orders: Mapped[list['Order']] = relationship(back_populates='product')
    purchases: Mapped[list['Purchase']] = relationship(back_populates='product')


class Order(Base):
    __tablename__ = 'orders'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    product_id: Mapped[int | None] = mapped_column(ForeignKey('products.id'), nullable=True)
    amount_usd: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    payment_method: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(30), default=OrderStatus.pending.value)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User] = relationship(back_populates='orders')
    product: Mapped[Product | None] = relationship(back_populates='orders')
    payment_request: Mapped['PaymentRequest | None'] = relationship(back_populates='order', uselist=False)
    purchase: Mapped['Purchase | None'] = relationship(back_populates='order', uselist=False)


class PaymentRequest(Base):
    __tablename__ = 'payment_requests'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    order_id: Mapped[int | None] = mapped_column(ForeignKey('orders.id'), nullable=True)
    kind: Mapped[str] = mapped_column(String(30), default='product_purchase')
    method: Mapped[str] = mapped_column(String(30), default=PaymentMethod.crypto.value)
    asset: Mapped[str] = mapped_column(String(30))
    network: Mapped[str] = mapped_column(String(30))
    receiving_address: Mapped[str] = mapped_column(String(255))
    expected_amount: Mapped[Decimal] = mapped_column(Numeric(18, 8))
    unique_amount: Mapped[Decimal] = mapped_column(Numeric(18, 8))
    status: Mapped[str] = mapped_column(String(30), default=OrderStatus.pending.value)
    tx_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    confirmations: Mapped[int] = mapped_column(Integer, default=0)
    qr_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    order: Mapped[Order | None] = relationship(back_populates='payment_request')


class Purchase(Base):
    __tablename__ = 'purchases'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    product_id: Mapped[int] = mapped_column(ForeignKey('products.id'))
    order_id: Mapped[int] = mapped_column(ForeignKey('orders.id'), unique=True)
    delivered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User] = relationship(back_populates='purchases')
    product: Mapped[Product] = relationship(back_populates='purchases')
    order: Mapped[Order] = relationship(back_populates='purchase')
