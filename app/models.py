from sqlalchemy import String, Float, Text
from sqlalchemy.orm import Mapped, mapped_column

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


class ChatHistory(Base):

    __tablename__ = "chat_history"

    user_id: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    # Przechowujemy całą historię rozmowy (listę dict) jako string JSON.
    # Używamy Text zamiast String dla dłuższych rozmów.
    history_json: Mapped[str] = mapped_column(Text, nullable=True)