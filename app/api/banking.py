from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

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
