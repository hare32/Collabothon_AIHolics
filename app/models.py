from typing import Optional
from sqlalchemy import String, Float, Integer, ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from datetime import datetime

from .db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    phone: Mapped[str] = mapped_column(String, nullable=False)


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    user_id: Mapped[str] = mapped_column(String, nullable=False)
    iban: Mapped[str] = mapped_column(String, nullable=False)
    balance: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String, default="PLN")


class Contact(Base):
    """
    Zapisany odbiorca przelewów (np. 'mama', 'wnuczek').
    """

    __tablename__ = "contacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)

    # np. 'mama', 'wnuczek', 'sąsiad'
    nickname: Mapped[str] = mapped_column(String, nullable=False)

    # pełne imię i nazwisko / nazwa
    full_name: Mapped[str] = mapped_column(String, nullable=False)

    # numer konta odbiorcy
    iban: Mapped[str] = mapped_column(String, nullable=False)

    # domyślny tytuł przelewu, jeśli brak innego
    default_title: Mapped[Optional[str]] = mapped_column(String, nullable=True)


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    sender_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)

    # dane odbiorcy zapisane w momencie przelewu
    recipient_name: Mapped[str] = mapped_column(String, nullable=False)
    recipient_iban: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)

    amount: Mapped[float] = mapped_column(Float, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
