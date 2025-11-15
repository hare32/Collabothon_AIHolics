# app/assistant.py
from typing import Optional, Tuple, List

from sqlalchemy.orm import Session

from . import banking
from .llm import detect_intent, ask_llm, extract_recipient
from .assistant_utils import (
    conversation_history,
    store_history,
    extract_amount,
    extract_history_limit,
    format_amount_pln,
)


def process_message(
    message: str, user_id: str, db: Session
) -> Tuple[str, Optional[str]]:
    """
    Main assistant logic:
    - intent detection
    - money transfer
    - balance check
    - transaction history
    - fallback to LLM

    Returns (reply, intent).
    """

    # conversation history for this user
    history = conversation_history[user_id]

    # ---------- INTENT DETECTION (with history) ----------
    intent = detect_intent(message, history)

    user = banking.get_user(db, user_id)
    account = banking.get_account_for_user(db, user_id)

    # ---------- INTENT: MAKE TRANSFER ----------
    if intent == "make_transfer":
        if account is None:
            reply = "I couldn't find an account for this user."
            return store_history(user_id, message, reply), intent

        amount = extract_amount(message)
        if amount <= 0:
            reply = (
                "I understand you want to make a transfer, but I couldn't detect the amount. "
                "Please say the amount, for example '50 PLN'."
            )
            return store_history(user_id, message, reply), intent

        # Extract recipient label from speech using LLM (e.g. 'mom', 'grandson')
        recipient_label = extract_recipient(message, history)
        if not recipient_label:
            reply = (
                "I didn't understand who the transfer should be sent to. "
                "For example, say 'send 50 PLN to my mom'."
            )
            return store_history(user_id, message, reply), intent

        # Map this label to a saved contact (mom -> Barbara Smith, etc.)
        contact = banking.resolve_contact(db, user_id, recipient_label)

        if not contact:
            reply = (
                f"I don't know the recipient '{recipient_label}'. "
                "Please add them as a saved contact in your banking app."
            )
            return store_history(user_id, message, reply), intent

        recipient_name = contact.full_name
        recipient_iban = contact.iban
        title = contact.default_title or f"Transfer to {contact.full_name}"
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
            # e.g. insufficient funds
            reply = str(e)
            return store_history(user_id, message, reply), intent

        reply = (
            f"A transfer of {amount:.2f} {updated.currency} has been executed "
            f"to: {pretty_label}. "
            f"Your current balance is {updated.balance:.2f} {updated.currency} "
            f"on account {updated.iban}."
        )
        return store_history(user_id, message, reply), intent

    # ---------- INTENT: CHECK BALANCE ----------
    if intent == "check_balance":
        if account is None:
            reply = "I couldn't find an account for this user."
        else:
            reply = (
                f"Your current balance is {account.balance:.2f} {account.currency} "
                f"on account {account.iban}."
            )
        return store_history(user_id, message, reply), intent

    # ---------- INTENT: SHOW HISTORY ----------
    if intent == "show_history":
        # how many last transfers? (default 3)
        limit = extract_history_limit(message, default=3, max_limit=10)
        transactions = banking.get_transactions_for_user(db, user_id, limit=limit)

        if not transactions:
            reply = "I couldn't find any transfers in your history."
            return store_history(user_id, message, reply), intent

        lines: List[str] = []
        for t in transactions:
            amount_text = format_amount_pln(t.amount)
            lines.append(
                f"Transfer of {amount_text} to {t.recipient_name}, " f"title: {t.title}"
            )

        reply = "Here are your recent transfers:\n" + "\n".join(lines)
        return store_history(user_id, message, reply), intent

    # ---------- OTHER QUESTIONS → LLM ----------
    context = ""
    if user:
        context += f"User: {user.name}\n"
    if account:
        context += (
            f"Balance: {account.balance:.2f} {account.currency} "
            f"on account {account.iban}\n"
        )

    reply = ask_llm(message, context)
    return store_history(user_id, message, reply), intent
