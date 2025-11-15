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
    Wykonuje nowy przelew.
    Tworzy zapis transakcji i aktualizuje saldo.
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
        # Błędy walidacji z banking.py (np. brak środków)
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/transactions/{user_id}", response_model=List[TransactionOut])
def get_transaction_history(user_id: str, db: Session = Depends(get_db)):
    """
    Zwraca historię transakcji dla danego użytkownika (gdzie był nadawcą).
    """
    transactions = banking.get_transactions_for_user(db, user_id)
    return transactions
