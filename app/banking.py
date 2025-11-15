from typing import Optional, Sequence

from sqlalchemy.orm import Session
from sqlalchemy import select, func as sa_func

from .models import User, Account, Transaction, Contact


def seed_data(db: Session) -> None:
    """Dodaje podstawowego użytkownika, konto, kontakty i historię, jeśli baza jest pusta."""
    if db.execute(select(User)).first():
        return

    # --- UŻYTKOWNIK ---
    user = User(id="user-1", name="Jan Kowalski", phone="+48123123123")
    db.add(user)

    # --- KONTO (startujemy z 4000, potem odejmiemy transakcje => wyjdzie ~2500) ---
    acc = Account(
        id="acc-1",
        user_id="user-1",
        iban="PL61109010140000071219812874",
        balance=4000.00,
        currency="PLN",
    )
    db.add(acc)

    # --- KONTAKTY (zapisani odbiorcy) ---
    contacts = [
        Contact(
            user_id="user-1",
            nickname="mama",
            full_name="Barbara Kowalska",
            iban="PL27114020040000300201355387",
            default_title="Przelew dla mamy",
        ),
        Contact(
            user_id="user-1",
            nickname="tata",
            full_name="Andrzej Kowalski",
            iban="PL02105000997603123456789123",
            default_title="Przelew dla taty",
        ),
        Contact(
            user_id="user-1",
            nickname="wnuczek",
            full_name="Maciej Nowak",
            iban="PL12116022020000000012345678",
            default_title="Prezent dla wnuczka",
        ),
        Contact(
            user_id="user-1",
            nickname="sąsiad",
            full_name="Adam Zieliński",
            iban="PL88114020040000300201399999",
            default_title="Pożyczka dla sąsiada",
        ),
        Contact(
            user_id="user-1",
            nickname="fundusz alimentacyjny",
            full_name="Fundusz Alimentacyjny",
            iban="PL12109010140000071219800000",
            default_title="Wpłata na fundusz alimentacyjny",
        ),
        Contact(
            user_id="user-1",
            nickname="spółdzielnia",
            full_name="Spółdzielnia Mieszkaniowa Zielona",
            iban="PL34175000120000000012345678",
            default_title="Czynsz za mieszkanie",
        ),
    ]
    for c in contacts:
        db.add(c)

    # --- 10 PRZYKŁADOWYCH TRANSAKCJI HISTORII ---
    initial_transactions = [
        (
            "Spółdzielnia Mieszkaniowa Zielona",
            "PL34175000120000000012345678",
            "Czynsz za mieszkanie",
            1200.0,
        ),
        (
            "PGE Obrót",
            "PL64102055581111123456789012",
            "Rachunek za prąd",
            100.0,
        ),
        (
            "Orange Polska",
            "PL27114020040000300201311111",
            "Abonament telefoniczny",
            60.0,
        ),
        (
            "UPC Polska",
            "PL30102055581111123456789099",
            "Internet w domu",
            40.0,
        ),
        (
            "Maciej Nowak",
            "PL12116022020000000012345678",
            "Prezent dla wnuczka",
            50.0,
        ),
        (
            "Kino Helios",
            "PL12105000997603123456789111",
            "Wyjście do kina",
            30.0,
        ),
        (
            "WOŚP",
            "PL30114020040000300201322222",
            "Darowizna na WOŚP",
            10.0,
        ),
        (
            "Adam Zieliński",
            "PL88114020040000300201399999",
            "Zwrot za zakupy",
            5.0,
        ),
        (
            "MPK Łódź",
            "PL27114020040000300201344444",
            "Bilet miesięczny",
            3.0,
        ),
        (
            "Fundusz Alimentacyjny",
            "PL12109010140000071219800000",
            "Wpłata na fundusz alimentacyjny",
            2.0,
        ),
    ]

    for name, iban, title, amount in initial_transactions:
        tx = Transaction(
            sender_id="user-1",
            recipient_name=name,
            recipient_iban=iban,
            title=title,
            amount=amount,
        )
        db.add(tx)
        acc.balance -= amount  # historia faktycznie obniża saldo

    db.commit()


def get_user(db: Session, user_id: str) -> Optional[User]:
    stmt = select(User).where(User.id == user_id)
    return db.execute(stmt).scalar_one_or_none()


def get_account_for_user(db: Session, user_id: str) -> Optional[Account]:
    stmt = select(Account).where(Account.user_id == user_id)
    return db.execute(stmt).scalar_one_or_none()


def resolve_contact(db: Session, user_id: str, label: str) -> Optional[Contact]:
    """
    Mapuje etykietę z mowy ('mama', 'fundusz alimentacyjny', 'sąsiad Maciek')
    na zapisany kontakt. Najpierw próbuje po nickname, potem po fragmencie full_name.
    """
    norm = label.strip().lower()
    if not norm:
        return None

    # Dokładne dopasowanie po nickname
    stmt = select(Contact).where(
        Contact.user_id == user_id,
        sa_func.lower(Contact.nickname) == norm,
    )
    contact = db.execute(stmt).scalar_one_or_none()
    if contact:
        return contact

    # Luźniejsze dopasowanie po pełnym imieniu/nazwie
    stmt2 = select(Contact).where(
        Contact.user_id == user_id,
        sa_func.lower(Contact.full_name).like(f"%{norm}%"),
    )
    contact = db.execute(stmt2).scalar_one_or_none()
    if contact:
        return contact

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
