from typing import Optional, Tuple, Dict, List
import re
from collections import defaultdict

from sqlalchemy.orm import Session

from . import banking
from .llm import detect_intent, ask_llm

# ======= PROSTA HISTORIA ROZMOWY PER USER =======
# Lista par: ("user" | "assistant", tekst)
conversation_history: Dict[str, List[Tuple[str, str]]] = defaultdict(list)


def _store_history(user_id: str, user_msg: str, reply: str) -> str:
    """
    Zapisuje ostatnią wypowiedź użytkownika i odpowiedź asystenta
    w historii dla danego usera. Trzymamy tylko ostatnie ~10 wymian.
    """
    history = conversation_history[user_id]
    history.append(("user", user_msg))
    history.append(("assistant", reply))
    # przycinamy, żeby nie rosło w nieskończoność
    if len(history) > 20:  # 10 wymian user–assistant
        del history[:-20]
    return reply


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

    # historia rozmowy dla tego usera
    history = conversation_history[user_id]

    # ---------- DETEKCJA INTENCJI (z historią) ----------
    intent = detect_intent(message, history)

    user = banking.get_user(db, user_id)
    account = banking.get_account_for_user(db, user_id)

    # ---------- INTENCJA: PRZELEW ----------
    if intent == "make_transfer":
        if account is None:
            reply = "Nie znaleziono konta dla tego użytkownika."
            return _store_history(user_id, message, reply), intent

        amount = extract_amount(message)
        if amount <= 0:
            reply = (
                "Rozumiem, że chcesz zrobić przelew, ale nie rozpoznałem kwoty. "
                "Podaj proszę kwotę, np. '50 zł'."
            )
            return _store_history(user_id, message, reply), intent

        try:
            updated = banking.perform_transfer(db, user_id, amount)
        except ValueError as e:
            # np. niewystarczające środki
            reply = str(e)
            return _store_history(user_id, message, reply), intent

        reply = (
            f"Przelew na kwotę {amount:.2f} {updated.currency} został wykonany. "
            f"Twoje aktualne saldo to {updated.balance:.2f} {updated.currency} "
            f"na koncie {updated.iban}."
        )
        return _store_history(user_id, message, reply), intent

    # ---------- INTENCJA: SPRAWDZENIE SALDA ----------
    if intent == "check_balance":
        if account is None:
            reply = "Nie znaleziono konta dla tego użytkownika."
        else:
            reply = (
                f"Twoje aktualne saldo wynosi {account.balance:.2f} {account.currency} "
                f"na koncie {account.iban}."
            )
        return _store_history(user_id, message, reply), intent

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
    return _store_history(user_id, message, reply), intent
