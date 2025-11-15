# app/assistant.py
from typing import Optional, Tuple, List

from sqlalchemy.orm import Session

from . import banking
from .llm import detect_intent, ask_llm, extract_recipient, refers_to_same_amount_as_last_time
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

        # 1. Najpierw odbiorca
        recipient_label = extract_recipient(message, history)
        if not recipient_label:
            reply = (
                "I didn't understand who the transfer should be sent to. "
                "For example, say 'send 50 PLN to my mom'."
            )
            return store_history(user_id, message, reply), intent

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

        # 2. Kwota
        amount = extract_amount(message)

        # jeśli kwoty brak → zapytaj LLM czy chodzi o "taką samą kwotę jak ostatnio"
        if amount is None or amount <= 0:
            if refers_to_same_amount_as_last_time(message, history):
                last_tx = banking.get_last_transfer_to_contact(
                    db, user_id, recipient_name
                )
                if last_tx:
                    amount = last_tx.amount

        # jeśli dalej brak sensownej kwoty → dopiero wtedy prosimy usera
        if amount is None or amount <= 0:
            reply = (
                "I understand you want to make a transfer, but I couldn't detect the amount. "
                "You can say, for example, '50 PLN' or 'for the same amount as last time to my mom'."
            )
            return store_history(user_id, message, reply), intent

        # 3. Właściwy przelew
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
            f"A transfer of {amount:.2f} {updated.currency} has been executed "
            f"to: {pretty_label}. "
            f"Your current balance is {updated.balance:.2f} {updated.currency} "
        )
        return store_history(user_id, message, reply), intent


    # ---------- INTENT: CHECK BALANCE ----------
    if intent == "check_balance":
        if account is None:
            reply = "I couldn't find an account for this user."
        else:
            reply = (
                f"Your current balance is {account.balance:.2f} {account.currency} "
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
        )

    reply = ask_llm(message, context)
    return store_history(user_id, message, reply), intent
