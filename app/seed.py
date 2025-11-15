# app/seed.py
from sqlalchemy.orm import Session
from sqlalchemy import select

from .models import User, Account, Transaction, Contact


def seed_demo_data(db: Session) -> None:
    """
    Adds a demo user, account, contacts and transaction history
    if the database is empty.
    """
    if db.execute(select(User)).first():
        return

    # --- USER ---
    user = User(
        id="user-1",
        name="John Smith",
        pesel="12345678901",  # demo data for auth
        pin_code="4321",  # demo PIN for auth
        phone="+48123123123",
    )
    db.add(user)

    # --- ACCOUNT (start at 4000, then subtract transactions => ~?)
    acc = Account(
        id="acc-1",
        user_id="user-1",
        iban="PL61109010140000071219812874",
        balance=4000.00,
        currency="PLN",
    )
    db.add(acc)

    # --- CONTACTS (saved recipients) ---
    contacts = [
        Contact(
            user_id="user-1",
            nickname="mom",
            full_name="Barbara Smith",
            iban="PL27114020040000300201355387",
            default_title="Transfer for mom",
        ),
        Contact(
            user_id="user-1",
            nickname="dad",
            full_name="Andrew Smith",
            iban="PL02105000997603123456789123",
            default_title="Transfer for dad",
        ),
        Contact(
            user_id="user-1",
            nickname="grandson",
            full_name="Michael Nowak",
            iban="PL12116022020000000012345678",
            default_title="Gift for grandson",
        ),
        Contact(
            user_id="user-1",
            nickname="neighbor",
            full_name="Adam Green",
            iban="PL88114020040000300201399999",
            default_title="Loan for neighbor",
        ),
        Contact(
            user_id="user-1",
            nickname="child_support_fund",
            full_name="Child Support Fund",
            iban="PL12109010140000071219800000",
            default_title="Payment to child support fund",
        ),
        # KLUCZOWY KONTAKT DO DEMA – RENT
        Contact(
            user_id="user-1",
            nickname="rent",  # <--- ważne, żeby LLM mógł skojarzyć "the rent"
            full_name="Green Housing Cooperative",
            iban="PL34175000120000000012345678",
            default_title="Apartment rent",
        ),
    ]
    for c in contacts:
        db.add(c)

    # --- SAMPLE HISTORY TRANSACTIONS ---
    # Pierwsza transakcja: czynsz 700 PLN do Green Housing Cooperative
    initial_transactions = [
        (
            "Green Housing Cooperative",
            "PL34175000120000000012345678",
            "Apartment rent",
            700.0,  # <--- kwota "jak w przykładzie"
        ),
        (
            "PGE Energy",
            "PL64102055581111123456789012",
            "Electricity bill",
            100.0,
        ),
        (
            "Orange Telecom",
            "PL27114020040000300201311111",
            "Phone subscription",
            60.0,
        ),
        (
            "UPC Internet",
            "PL30102055581111123456789099",
            "Home internet",
            40.0,
        ),
        (
            "Michael Nowak",
            "PL12116022020000000012345678",
            "Gift for grandson",
            50.0,
        ),
        (
            "Helios Cinema",
            "PL12105000997603123456789111",
            "Cinema night",
            30.0,
        ),
        (
            "Charity WOŚP",
            "PL30114020040000300201322222",
            "Charity donation",
            10.0,
        ),
        (
            "Adam Green",
            "PL88114020040000300201399999",
            "Shopping refund",
            5.0,
        ),
        (
            "MPK Lodz",
            "PL27114020040000300201344444",
            "Monthly ticket",
            3.0,
        ),
        (
            "Child Support Fund",
            "PL12109010140000071219800000",
            "Payment to child support fund",
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
        acc.balance -= amount  # history actually reduces the balance

    db.commit()
