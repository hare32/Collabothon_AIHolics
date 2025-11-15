from typing import Optional, Tuple, Dict, List
import re
from collections import defaultdict

from sqlalchemy.orm import Session

from . import banking
from .llm import detect_intent, ask_llm

# ======= SIMPLE PER-USER CONVERSATION HISTORY =======
# List of pairs: ("user" | "assistant", text)
conversation_history: Dict[str, List[Tuple[str, str]]] = defaultdict(list)


def _store_history(user_id: str, user_msg: str, reply: str) -> str:
    """
    Stores the user's last message and the assistant's reply
    in that user's history. We keep only the last ~10 exchanges.
    """
    history = conversation_history[user_id]
    history.append(("user", user_msg))
    history.append(("assistant", reply))

    # Trim the history so it doesn't grow indefinitely
    if len(history) > 20:  # 10 user–assistant exchanges
        del history[:-20]

    return reply


def extract_amount(message: str) -> float:
    """
    Very simple amount parser.
    Finds the first number in text, e.g.:
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
    Main assistant logic:
    - intent detection
    - transfers
    - balance inquiries
    - fallback to LLM

    Returns (reply, intent).
    """

    # Conversation history for this user
    history = conversation_history[user_id]

    # ---------- INTENT DETECTION (with history) ----------
    intent = detect_intent(message, history)

    user = banking.get_user(db, user_id)
    account = banking.get_account_for_user(db, user_id)

    # ---------- INTENT: MAKE TRANSFER ----------
    if intent == "make_transfer":
        if account is None:
            reply = "No account found for this user."
            return _store_history(user_id, message, reply), intent

        amount = extract_amount(message)
        if amount <= 0:
            reply = (
                "I understand you want to make a transfer, but I couldn't detect the amount. "
                "Please provide it, for example: '50 dollars'."
            )
            return _store_history(user_id, message, reply), intent

        try:
            updated = banking.perform_transfer(db, user_id, amount)
        except ValueError as e:
            # e.g. insufficient funds
            reply = str(e)
            return _store_history(user_id, message, reply), intent

        reply = (
            f"A transfer of {amount:.2f} {updated.currency} has been completed. "
            f"Your current balance is {updated.balance:.2f} {updated.currency} "
            f"on account {updated.iban}."
        )
        return _store_history(user_id, message, reply), intent

    # ---------- INTENT: CHECK BALANCE ----------
    if intent == "check_balance":
        if account is None:
            reply = "No account found for this user."
        else:
            reply = (
                f"Your current balance is {account.balance:.2f} {account.currency} "
                f"on account {account.iban}."
            )
        return _store_history(user_id, message, reply), intent

    # ---------- OTHER QUESTIONS → FALLBACK TO LLM ----------
    context = ""
    if user:
        context += f"User: {user.name}\n"
    if account:
        context += (
            f"Balance: {account.balance:.2f} {account.currency} "
            f"on account {account.iban}\n"
        )

    reply = ask_llm(message, context)
    return _store_history(user_id, message, reply), intent
