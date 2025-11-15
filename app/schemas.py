from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime


class ChatRequest(BaseModel):
    user_id: str
    message: str


class ChatResponse(BaseModel):
    reply: str
    intent: Optional[str]


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    phone: str


class AccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    user_id: str
    iban: str
    balance: float
    currency: str


class TransferRequest(BaseModel):
    user_id: str  # Nadawca
    amount: float
    recipient_details: str


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sender_id: str
    recipient_details: str
    amount: float
    timestamp: datetime