# app/assistant_utils.py
from typing import Dict, List, Tuple
from collections import defaultdict
from dataclasses import dataclass
import re


# ======= SIMPLE PER-USER CONVERSATION HISTORY =======
# List of pairs: ("user" | "assistant", text)
ConversationHistory = Dict[str, List[Tuple[str, str]]]
conversation_history: ConversationHistory = defaultdict(list)


def store_history(user_id: str, user_msg: str, reply: str) -> str:
    """
    Stores the last user message and assistant reply
    in the history for a given user. We keep only ~10 turns.
    """
    history = conversation_history[user_id]
    history.append(("user", user_msg))
    history.append(("assistant", reply))
    if len(history) > 20:  # 10 user–assistant exchanges
        del history[:-20]
    return reply


def extract_amount(message: str) -> float:
    """
    Very simple amount parser from text.
    Looks for the first number in the text:
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
    Simple formatter for amount in PLN for spoken output.
    """
    if amount.is_integer():
        return f"{int(amount)} PLN"
    return f"{amount:.2f} PLN"


def extract_history_limit(message: str, default: int = 3, max_limit: int = 10) -> int:
    """
    Extracts from the utterance how many last transfers to show.
    Examples: 'show last 3 transfers', 'give me 5 last transactions'.
    If no number found -> default.
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


# ======= PENDING TRANSFER STATE (for confirmations) =======


@dataclass
class PendingTransfer:
    user_id: str
    amount: float
    recipient_name: str
    recipient_iban: str
    title: str
    currency: str
    # 1 = pierwsze pytanie o potwierdzenie, 2 = ostateczne potwierdzenie
    confirmation_stage: int = 0


# Per-user pending transfer waiting for confirmation
pending_transfers: Dict[str, PendingTransfer] = {}
