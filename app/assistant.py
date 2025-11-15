from typing import Optional, Tuple, Dict, List
import re
from collections import defaultdict

from sqlalchemy.orm import Session

from . import banking
from .llm import detect_intent, ask_llm, extract_recipient

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


def _format_amount_pln(amount: float) -> str:
    """
    Prosty formatter kwoty w złotówkach do użycia w mowie.
    """
    if amount.is_integer():
        return f"{int(amount)} złotych"
    return f"{amount:.2f} złotego"


def process_message(
    message: str, user_id: str, db: Session
) -> Tuple[str, Optional[str]]:
    """
    Wspólna logika asystenta:
    - intencje
    - przelew
    - saldo
    - historia przelewów
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

        # Wyciągamy nazwę odbiorcy z mowy za pomocą LLM (np. 'mama', 'wnuczek')
        recipient_label = extract_recipient(message, history)
        if not recipient_label:
            reply = (
                "Nie zrozumiałem, do kogo ma być przelew. "
                "Powiedz na przykład 'wyślij 50 zł do mamy'."
            )
            return _store_history(user_id, message, reply), intent

        # Mapujemy to na zapisany kontakt (mama -> Barbara Kowalska, itd.)
        contact = banking.resolve_contact(db, user_id, recipient_label)

        if not contact:
            reply = (
                f"Nie znam odbiorcy '{recipient_label}'. "
                "Dodaj go proszę w aplikacji bankowej jako zapisany kontakt."
            )
            return _store_history(user_id, message, reply), intent

        recipient_name = contact.full_name
        recipient_iban = contact.iban
        title = contact.default_title or f"Przelew do {contact.full_name}"
        pretty_label = f"{contact.full_name} ({contact.nickname})"

        try:
            updated = banking.perform_transfer(
                db,
                user_id=user_id,
                amount=amount,
                recipient_name=recipient_name,
                recipient_iban=recipient_iban,
                title=title,
            )
        except ValueError as e:
            # np. niewystarczające środki
            reply = str(e)
            return _store_history(user_id, message, reply), intent

        reply = (
            f"Przelew na kwotę {amount:.2f} {updated.currency} został wykonany "
            f"do odbiorcy: {pretty_label}. "
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

    # ---------- INTENCJA: HISTORIA PRZELEWÓW ----------
    if intent == "show_history":
        # Dla prostoty: pokażmy 3 ostatnie przelewy
        transactions = banking.get_transactions_for_user(db, user_id, limit=3)

        if not transactions:
            reply = "Nie znalazłem żadnych przelewów w historii."
            return _store_history(user_id, message, reply), intent

        lines: List[str] = []
        for t in transactions:
            kwota_txt = _format_amount_pln(t.amount)
            lines.append(
                f"Przelew na kwotę {kwota_txt} do {t.recipient_name}, "
                f"tytuł: {t.title}"
            )

        reply = "Oto Twoje ostatnie przelewy:\n" + "\n".join(lines)
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
