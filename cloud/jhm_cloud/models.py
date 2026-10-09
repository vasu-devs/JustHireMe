from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def now():
    return datetime.now(timezone.utc)


def uid():
    return str(uuid4())


class Base(DeclarativeBase):
    pass


class Account(Base):
    __tablename__ = "mobile_accounts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    purchase_token: Mapped[str] = mapped_column(String(36), unique=True, default=uid)
    balance: Mapped[int] = mapped_column(Integer, default=0)
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    auth_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    profile: Mapped[dict] = mapped_column(JSON, default=dict)


class Job(Base):
    __tablename__ = "mobile_jobs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    account_id: Mapped[str] = mapped_column(ForeignKey("mobile_accounts.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    company: Mapped[str] = mapped_column(String(200))
    location: Mapped[str] = mapped_column(String(200), default="")
    url: Mapped[str] = mapped_column(String(2000), default="")
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="saved")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Purchase(Base):
    __tablename__ = "mobile_purchases"
    id: Mapped[str] = mapped_column(String(150), primary_key=True)  # environment:transactionID
    account_id: Mapped[str] = mapped_column(ForeignKey("mobile_accounts.id"), index=True)
    product_id: Mapped[str] = mapped_column(String(200))
    credits: Mapped[int] = mapped_column(Integer)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    expires_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    signed_ms: Mapped[int] = mapped_column(BigInteger)


class Entry(Base):
    __tablename__ = "mobile_ledger"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    account_id: Mapped[str] = mapped_column(ForeignKey("mobile_accounts.id"), index=True)
    key: Mapped[str] = mapped_column(String(200), unique=True)
    amount: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Operation(Base):
    __tablename__ = "mobile_operations"
    __table_args__ = (UniqueConstraint("account_id", "request_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    account_id: Mapped[str] = mapped_column(ForeignKey("mobile_accounts.id"), index=True)
    request_key: Mapped[str] = mapped_column(String(36))
    fingerprint: Mapped[str] = mapped_column(String(64))
    job_id: Mapped[str] = mapped_column(String(36))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    cost: Mapped[int] = mapped_column(Integer)
    result: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
