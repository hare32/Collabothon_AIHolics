# app/banking.py
from typing import Optional, Sequence

from sqlalchemy.orm import Session
from sqlalchemy import select

from .models import User, Account, Transaction, Contact
from .llm import match_contact_label


def get_user(db: Session, user_id: str) -> Optional[User]:
    stmt = select(User).where(User.id == user_id)
    return db.execute(stmt).scalar_one_or_none()


def get_account_for_user(db: Session, user_id: str) -> Optional[Account]:
    stmt = select(Account).where(Account.user_id == user_id)
    return db.execute(stmt).scalar_one_or_none()


def resolve_contact(db: Session, user_id: str, label: str) -> Optional[Contact]:
    """
    Używa LLM (match_contact_label), żeby dopasować frazę z mowy do jednego z kontaktów.
    Przykład:
      label: 'do mojej mamy'  -> LLM wybiera nickname 'mama'  -> kontakt 'Barbara Kowalska'
    """
    label = (label or "").strip()
    if not label:
        return None

    stmt = select(Contact).where(Contact.user_id == user_id)
    contacts = db.execute(stmt).scalars().all()
    if not contacts:
        return None

    contact_dicts = [
        {"nickname": c.nickname, "full_name": c.full_name} for c in contacts
    ]

    chosen = match_contact_label(label, contact_dicts)
    if not chosen:
        return None

    chosen_lower = chosen.strip().lower()

    # najpierw spróbuj po nickname (case-insensitive)
    for c in contacts:
        if c.nickname.lower() == chosen_lower:
            return c

    # jeśli model zwrócił pełną nazwę zamiast nickname, spróbuj po full_name
    for c in contacts:
        if c.full_name.lower() == chosen_lower:
            return c

    return None


def perform_transfer(
    db: Session,
    user_id: str,
    amount: float,
    recipient_name: str,
    recipient_iban: str,
    title: str,
) -> Account:
    """
    Wykonuje przelew (odejmuje saldo) i tworzy zapis transakcji
    z pełnymi danymi odbiorcy.
    """
    account = get_account_for_user(db, user_id)
    if account is None:
        raise ValueError("Brak konta dla użytkownika.")

    if amount <= 0:
        raise ValueError("Kwota przelewu musi być dodatnia.")

    if account.balance < amount:
        raise ValueError("Niewystarczające środki na koncie.")

    if not recipient_name:
        raise ValueError("Brak nazwy odbiorcy.")

    if not recipient_iban:
        # w prawdziwym banku byłby twardy błąd
        raise ValueError("Brak numeru konta odbiorcy.")

    account.balance -= amount

    new_transaction = Transaction(
        sender_id=user_id,
        recipient_name=recipient_name,
        recipient_iban=recipient_iban,
        title=title,
        amount=amount,
    )
    db.add(new_transaction)

    db.commit()
    db.refresh(account)

    return account


def get_transactions_for_user(
    db: Session,
    user_id: str,
    limit: Optional[int] = None,
) -> Sequence[Transaction]:
    """
    Pobiera historię transakcji, gdzie użytkownik był NADAWCĄ.
    Jeśli podano limit, zwraca maksymalnie 'limit' najnowszych transakcji.
    """
    stmt = (
        select(Transaction)
        .where(Transaction.sender_id == user_id)
        .order_by(Transaction.timestamp.desc())
    )

    if limit is not None:
        stmt = stmt.limit(limit)

    return db.execute(stmt).scalars().all()
