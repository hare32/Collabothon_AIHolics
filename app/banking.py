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
    Uses LLM (match_contact_label) to map a phrase from speech to one of the contacts.
    Example:
      label: 'to my mom'  -> LLM picks nickname 'mom'  -> contact 'Barbara Smith'
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

    # Try by nickname first (case-insensitive)
    for c in contacts:
        if c.nickname.lower() == chosen_lower:
            return c

    # If the model returned full name instead of nickname, try by full_name
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
    Performs a transfer (subtracts balance) and creates a transaction record
    with full recipient data.
    """
    account = get_account_for_user(db, user_id)
    if account is None:
        raise ValueError("No account found for this user.")

    if amount <= 0:
        raise ValueError("Transfer amount must be positive.")

    if account.balance < amount:
        raise ValueError("Insufficient funds on the account.")

    if not recipient_name:
        raise ValueError("Recipient name is missing.")

    if not recipient_iban:
        # in a real bank this would be a hard error
        raise ValueError("Recipient IBAN is missing.")

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
    Returns transaction history where the user is the SENDER.
    If limit is provided, returns at most 'limit' most recent transactions.
    """
    stmt = (
        select(Transaction)
        .where(Transaction.sender_id == user_id)
        .order_by(Transaction.timestamp.desc())
    )

    if limit is not None:
        stmt = stmt.limit(limit)

    return db.execute(stmt).scalars().all()
