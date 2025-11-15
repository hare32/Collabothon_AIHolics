from typing import List
from typing import Optional, Sequence
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional, Sequence
from sqlalchemy.orm import Session
from sqlalchemy import select

from ..models import User, Account, Transaction, Contact
from ..llm import match_contact_label
from ..db import get_db
from .. import banking
from ..schemas import TransactionOut, TransferRequest, AccountOut

router = APIRouter(prefix="/banking", tags=["banking"])


@router.post("/transfer", response_model=AccountOut)
def create_transfer(request: TransferRequest, db: Session = Depends(get_db)):
    """
    Performs a new transfer.
    Creates a transaction record and updates the account balance.
    """
    try:
        account = banking.perform_transfer(
            db,
            user_id=request.user_id,
            amount=request.amount,
            recipient_name=request.recipient_name,
            recipient_iban=request.recipient_iban,
            title=request.title,
        )
        return account
    except ValueError as e:
        # Validation errors from banking.py (e.g. insufficient funds)
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/transactions/{user_id}", response_model=List[TransactionOut])
def get_transaction_history(user_id: str, db: Session = Depends(get_db)):
    """
    Returns the transaction history for a given user (where the user is the sender).
    """
    transactions = banking.get_transactions_for_user(db, user_id)
    return transactions


def get_last_transfer_to_contact(
    db: Session,
    user_id: str,
    recipient_name: str,
) -> Optional[Transaction]:
    """
    Zwraca ostatni przelew do danego odbiorcy (po nazwie), jeśli istnieje.
    """
    stmt = (
        select(Transaction)
        .where(
            Transaction.sender_id == user_id,
            Transaction.recipient_name == recipient_name,
        )
        .order_by(Transaction.timestamp.desc())
        .limit(1)
    )
    return db.execute(stmt).scalars().first()