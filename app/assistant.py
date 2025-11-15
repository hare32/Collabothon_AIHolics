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


# =====================================================
#               MAIN ASSISTANT LOGIC
# =====================================================

def process_message(
    message: str, user_id: str, db: Session
) -> Tuple[str, Optional[str]]:

    user = banking.get_user(db, user_id)
    account = banking.get_account_for_user(db, user_id)

    # conversation history for this user
    history = conversation_history[user_id]

    # ---------- INTENT DETECTION ----------
    intent = detect_intent(message, history)

    # ---------- MAKE TRANSFER ----------
    if intent == "make_transfer":
        if account is None:
            reply = "I couldn't find an account for this user."
            return store_history(user_id, message, reply), intent

        amount = extract_amount(message)
        if amount <= 0:
            reply = (
                "I understand you want to make a transfer, but I couldn't detect the amount. "
                "Please say: 'Send 50 PLN to my mom'."
            )
            return store_history(user_id, message, reply), intent

        # Extract recipient label from speech using LLM
        recipient_label = extract_recipient(message, history)
        if not recipient_label:
            reply = (
                "I didn't understand who the transfer should be sent to. "
                "For example: 'Send 50 PLN to my neighbor'."
            )
            return store_history(user_id, message, reply), intent

        # Resolve saved contact
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
            reply = str(e)
            return store_history(user_id, message, reply), intent

        reply = (
            f"A transfer of {amount:.2f} {updated.currency} has been executed to {pretty_label}. "
            f"Your current balance is {updated.balance:.2f} {updated.currency} "
            f"on account {updated.iban}."
        )

        return store_history(user_id, message, reply), intent

    # ---------- CHECK BALANCE ----------
    if intent == "check_balance":
        if account is None:
            reply = "I couldn't find an account for this user."
        else:
            reply = (
                f"Your current balance is {account.balance:.2f} {account.currency} "
                f"on account {account.iban}."
            )
        return store_history(user_id, message, reply), intent

    # ---------- SHOW HISTORY ----------
    if intent == "show_history":
        limit = extract_history_limit(message, default=3, max_limit=10)
        transactions = banking.get_transactions_for_user(db, user_id, limit=limit)

        if not transactions:
            reply = "I couldn't find any transfers in your history."
            return store_history(user_id, message, reply), intent

        lines = []
        for t in transactions:
            amount_text = format_amount_pln(t.amount)
            lines.append(
                f"Transfer of {amount_text} to {t.recipient_name}, title: {t.title}"
            )

        reply = "Here are your recent transfers:\n" + "\n".join(lines)
        return store_history(user_id, message, reply), intent

    # ---------- OTHER QUESTIONS (LLM fallback) ----------
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
