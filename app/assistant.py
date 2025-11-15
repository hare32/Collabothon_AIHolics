# app/assistant.py
from typing import Optional, Tuple, Dict, List
import re
from collections import defaultdict
from sqlalchemy.orm import Session

from . import banking
from .llm import detect_intent, ask_llm

# ======= STATE =======
conversation_history: Dict[str, List[Tuple[str, str]]] = defaultdict(list)

auth_step: Dict[str, int] = defaultdict(int)
# 0 = need full name
# 1 = need last4 of PESEL
# 2 = need PIN
# 3 = authenticated OK

auth_failures: Dict[str, int] = defaultdict(int)  # counts total failures (secret)

MAX_ATTEMPTS = 3


def _store_history(user_id: str, user_msg: str, reply: str) -> str:
    history = conversation_history[user_id]
    history.append(("user", user_msg))
    history.append(("assistant", reply))
    if len(history) > 20:
        del history[:-20]
    return reply


def extract_amount(message: str) -> float:
    m = re.search(r"(\d+[,.]?\d*)", message.replace(" ", ""))
    if not m:
        return 0.0
    try:
        return float(m.group(1).replace(",", "."))
    except ValueError:
        return 0.0


# =====================================================
#               AUTHENTICATION STEPS
# =====================================================
def authenticate_step(message: str, user, user_id: str) -> Tuple[str, str]:
    """Returns (reply, intent)."""
    msg = message.lower().replace(" ", "")

    # Too many failures → end session
    if auth_failures[user_id] >= MAX_ATTEMPTS:
        return (
            "I’m unable to verify your identity. For your security, the call will now end.",
            "auth_failed",
        )

    # =====================================================
    # STEP 0 → FULL NAME
    # =====================================================
    if auth_step[user_id] == 0:
        full_name = user.name.lower().replace(" ", "")
        if full_name in msg:
            auth_step[user_id] = 1
            return (
                "Thank you. Please say the last four digits of your national identification number.",
                "auth_continue",
            )
        else:
            auth_failures[user_id] += 1
            return (
                "I couldn’t verify your name. Please repeat your full name.",
                "auth_continue",
            )

    # =====================================================
    # STEP 1 → LAST 4 PESEL
    # =====================================================
    if auth_step[user_id] == 1:
        last4 = user.pesel[-4:]
        if last4 in msg:
            auth_step[user_id] = 2
            return (
                "Identification confirmed. Now please say your four digit PIN.",
                "auth_continue",
            )
        else:
            auth_failures[user_id] += 1
            return (
                "The identification digits do not match our records. Please repeat them.",
                "auth_continue",
            )

    # =====================================================
    # STEP 2 → PIN
    # =====================================================
    if auth_step[user_id] == 2:
        if user.pin_code in msg:
            auth_step[user_id] = 3
            return (
                "Authentication successful.",
                "auth_success",
            )
        else:
            auth_failures[user_id] += 1
            return (
                "The PIN you provided is incorrect. Please repeat your PIN.",
                "auth_continue",
            )

    return "Unexpected authentication state.", "auth_failed"


# =====================================================
#                MAIN ASSISTANT LOGIC
# =====================================================
def process_message(
    message: str, user_id: str, db: Session
) -> Tuple[str, Optional[str]]:

    user = banking.get_user(db, user_id)
    account = banking.get_account_for_user(db, user_id)

    # ---------------- AUTHENTICATION REQUIRED ----------------
    if auth_step[user_id] < 3:
        return authenticate_step(message, user, user_id)

    # ---------------- NORMAL OPERATION ----------------
    history = conversation_history[user_id]
    intent = detect_intent(message, history)

    # ---------- TRANSFER ----------
    if intent == "make_transfer":
        if account is None:
            reply = "No account found for this user."
            return _store_history(user_id, message, reply), intent

        amount = extract_amount(message)
        if amount <= 0:
            reply = (
                "I understand you want to make a transfer, but I couldn't detect the amount. "
                "Try for example: 'Send 50 dollars'."
            )
            return _store_history(user_id, message, reply), intent

        try:
            updated = banking.perform_transfer(db, user_id, amount)
        except ValueError as e:
            reply = str(e)
            return _store_history(user_id, message, reply), intent

        reply = (
            f"A transfer of {amount:.2f} {updated.currency} was completed. "
            f"Your new balance is {updated.balance:.2f} {updated.currency} "
            f"on account {updated.iban}."
        )
        return _store_history(user_id, message, reply), intent

    # ---------- CHECK BALANCE ----------
    if intent == "check_balance":
        if account is None:
            reply = "No account found for this user."
        else:
            reply = (
                f"Your current balance is {account.balance:.2f} {account.currency} "
                f"on account {account.iban}."
            )
        return _store_history(user_id, message, reply), intent

    # ---------- OTHER → LLM ----------
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
