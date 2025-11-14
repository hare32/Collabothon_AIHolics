from typing import Optional, Tuple
import re

from sqlalchemy.orm import Session

from . import banking
from .llm import detect_intent, ask_llm


def extract_amount(message: str) -> float:
    """
    Bardzo prosty parser kwoty z tekstu.
    Szuka pierwszej liczby w tekście:
    - 100
    - 100,50
    - 100.50
    """
    m = re.search(r"(\d+[,.]?\d*)", message.replace(" ", ""))
    if not m:
        return 0.0
    try:
        return float(m.group(1).replace(",", "."))
    except ValueError:
        return 0.0


def process_message(
    message: str, user_id: str, db: Session
) -> Tuple[str, Optional[str]]:
    """
    Wspólna logika asystenta:
    - intencje
    - przelew
    - saldo
    - fallback do LLM

    Zwraca (reply, intent).
    """
    intent = detect_intent(message)
    user = banking.get_user(db, user_id)
    account = banking.get_account_for_user(db, user_id)

    # ---------- INTENCJA: PRZELEW ----------
    if intent == "make_transfer":
        if account is None:
            return "Nie znaleziono konta dla tego użytkownika.", intent

        amount = extract_amount(message)
        if amount <= 0:
            return "Nie udało mi się rozpoznać poprawnej kwoty przelewu.", intent

        try:
            updated = banking.perform_transfer(db, user_id, amount)
        except ValueError as e:
            # np. niewystarczające środki
            return str(e), intent

        reply = (
            f"Przelew na kwotę {amount:.2f} {updated.currency} został wykonany. "
            f"Twoje aktualne saldo to {updated.balance:.2f} {updated.currency} "
            f"na koncie {updated.iban}."
        )
        return reply, intent

    # ---------- INTENCJA: SPRAWDZENIE SALDA ----------
    if intent == "check_balance":
        if account is None:
            reply = "Nie znaleziono konta dla tego użytkownika."
        else:
            reply = (
                f"Twoje aktualne saldo wynosi {account.balance:.2f} {account.currency} "
                f"na koncie {account.iban}."
            )
        return reply, intent

    # ---------- POZOSTAŁE PYTANIA → LLM ----------
    context = ""
    if user:
        context += f"Użytkownik: {user.name}\n"
    if account:
        context += (
            f"Saldo: {account.balance:.2f} {account.currency} "
            f"na koncie {account.iban}\n"
        )

    reply = ask_llm(message, context)
    return reply, intent
