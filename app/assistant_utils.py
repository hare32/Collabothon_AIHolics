# app/assistant_utils.py
from typing import Dict, List, Tuple
from collections import defaultdict
import re


# ======= PROSTA HISTORIA ROZMOWY PER USER =======
# Lista par: ("user" | "assistant", tekst)
ConversationHistory = Dict[str, List[Tuple[str, str]]]
conversation_history: ConversationHistory = defaultdict(list)


def store_history(user_id: str, user_msg: str, reply: str) -> str:
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


def format_amount_pln(amount: float) -> str:
    """
    Prosty formatter kwoty w złotówkach do użycia w mowie.
    """
    if amount.is_integer():
        return f"{int(amount)} złotych"
    return f"{amount:.2f} złotego"


def extract_history_limit(message: str, default: int = 3, max_limit: int = 10) -> int:
    """
    Wyciąga z wypowiedzi ile ostatnich przelewów pokazać.
    Np. 'podaj 3 ostatnie przelewy', 'pokaż 5 przelewów z historii'.
    Jeśli brak liczby -> default.
    """
    m = re.search(r"(\d+)", message)
    if not m:
        return default

    try:
        n = int(m.group(1))
    except ValueError:
        return default

    if n <= 0:
        return default

    return min(n, max_limit)
