from typing import Optional, Tuple

from sqlalchemy.orm import Session

from . import banking
from .llm import get_contextual_response



def process_message(
        message: str, user_id: str, db: Session
) -> Tuple[str, Optional[str]]:
    """
    Wspólna logika asystenta oparta o MCP:
    1. Pyta LLM (z pełną historią) o intencje i dane (JSON).
    2. Wykonuje akcje bankowe (pluginy) na podstawie odpowiedzi LLM.
    3. Zwraca finalną odpowiedź do użytkownika.
    """

    # 1. Zdobądź odpowiedź z LLM (który ma pamięć MCP)
    # Ta funkcja (z llm.py) już zaktualizowała historię w DB
    llm_resp = get_contextual_response(db, user_id, message)

    intent = llm_resp.get("intent", "other")
    # To jest szablon odpowiedzi, np. "Pana saldo to [SALDO]"
    reply_template = llm_resp.get("reply", "Przepraszam, nie zrozumiałem.")

    final_reply = reply_template  # Domyślna odpowiedź, jeśli nic nie robimy

    # 2. Wykonaj akcje bankowe ("pluginy") na podstawie intencji z JSON-a

    # ---------- INTENCJA: PRZELEW ----------
    if intent == "make_transfer":
        account = banking.get_account_for_user(db, user_id)
        if account is None:
            return "Nie znaleziono konta dla tego użytkownika.", intent

        # LLM wyciągnął kwotę za nas
        amount = llm_resp.get("amount")

        if not isinstance(amount, (int, float)) or amount <= 0:
            # Jeśli AI nie wyciągnęło kwoty, po prostu zwróci tekst
            # (np. "Komu chcesz przelać?"), który jest już w final_reply
            pass
        else:
            try:
                updated = banking.perform_transfer(db, user_id, amount)
                # Wypełnij szablon odpowiedzi prawdziwymi danymi
                final_reply = reply_template.replace(
                    "[SALDO]", f"{updated.balance:.2f} {updated.currency}"
                )
            except ValueError as e:
                # np. niewystarczające środki
                final_reply = str(e)

    # ---------- INTENCJA: SPRAWDZENIE SALDA ----------
    elif intent == "check_balance":
        account = banking.get_account_for_user(db, user_id)
        if account is None:
            final_reply = "Nie znaleziono konta dla tego użytkownika."
        else:
            # Wypełnij szablon odpowiedzi prawdziwymi danymi
            final_reply = reply_template.replace(
                "[SALDO]", f"{account.balance:.2f} {account.currency}"
            )

    # ---------- POZOSTAŁE PYTANIA (intent == "other") ----------
    # Po prostu zwracamy odpowiedź wygenerowaną przez LLM
    # (np. "Cześć, w czym mogę pomóc?"),
    # która jest już w `final_reply`

    return final_reply, intent