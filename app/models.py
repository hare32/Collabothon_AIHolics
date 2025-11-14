from sqlalchemy import Column, String, Float
from .db import Base


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    phone = Column(String, nullable=False)


class Account(Base):
    __tablename__ = "accounts"

    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, nullable=False)
    iban = Column(String, nullable=False)
    balance = Column(Float, nullable=False)
    currency = Column(String, default="PLN")
