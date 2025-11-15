from typing import Optional, Sequence

from sqlalchemy.orm import Session
from sqlalchemy import select
from .models import User, Account, Transaction


def seed_data(db: Session) -> None:
    """Dodaje podstawowego użytkownika i konto, jeśli baza jest pusta."""
    if db.execute(select(User)).first():
        return

    user = User(id="user-1", name="Jan Kowalski", phone="+48123123123")
    db.add(user)

    acc = Account(
        id="acc-1",
        user_id="user-1",
        iban="PL00123456789012345678901234",
        balance=2500.00,
        currency="PLN",
    )
    db.add(acc)

    db.commit()


def get_user(db: Session, user_id: str) -> Optional[User]:
    stmt = select(User).where(User.id == user_id)
    return db.execute(stmt).scalar_one_or_none()


def get_account_for_user(db: Session, user_id: str) -> Optional[Account]:
    stmt = select(Account).where(Account.user_id == user_id)
    return db.execute(stmt).scalar_one_or_none()


def perform_transfer(
    db: Session,
    user_id: str,
    amount: float,
    recipient_details: str = "Nieznany odbiorca (asystent głosowy)",
) -> Account:
    """
    Wykonuje przelew (odejmuje saldo) I twprzy zapis transakcji.
    Waliduje środki i kwotę.
    """
    account = get_account_for_user(db, user_id)
    if account is None:
        raise ValueError("Brak konta dla użytkownika.")

    if amount <= 0:
        raise ValueError("Kwota przelewu musi być dodatnia.")

    if account.balance < amount:
        raise ValueError("Niewystarczające środki na koncie.")

    account.balance -= amount

    new_transaction = Transaction(
        sender_id=user_id,
        recipient_details=recipient_details,
        amount=amount,
    )
    db.add(new_transaction)

    db.commit()
    db.refresh(account)

    return account


def get_transactions_for_user(db: Session, user_id: str) -> Sequence[Transaction]:
    """
    Pobiera historię transakcji, gdzie użytkownik był NADAWCĄ.
    """
    stmt = (
        select(Transaction)
        .where(Transaction.sender_id == user_id)
        .order_by(Transaction.timestamp.desc())
    )
    return db.execute(stmt).scalars().all()
