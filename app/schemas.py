from pydantic import BaseModel
from typing import Optional, Literal

# ---- Assistant ----


class ChatRequest(BaseModel):
    user_id: str
    message: str


class ChatResponse(BaseModel):
    reply: str
    intent: Optional[Literal["check_balance", "make_transfer", "other"]]


# ---- Banking ----


class UserOut(BaseModel):
    id: str
    name: str
    phone: str


class AccountOut(BaseModel):
    id: str
    user_id: str
    iban: str
    balance: float
    currency: str
