# app/assistant.py
from typing import Optional, Tuple, List

from sqlalchemy.orm import Session

from . import banking
from .llm import (
    detect_intent,
    ask_llm,
    extract_recipient,
    refers_to_same_amount_as_last_time,
    detect_confirmation_or_end,
)
from .assistant_utils import (
    conversation_history,
    store_history,
    extract_amount,
    extract_history_limit,
    format_amount_pln,
    pending_transfers,
    PendingTransfer,
)


def process_message(
    message: str, user_id: str, db: Session
) -> Tuple[str, Optional[str], bool]:
    """
    Main assistant logic:
    - intent detection
    - money transfer (with confirmation steps)
    - balance check
    - transaction history
    - fallback to LLM

    Returns (reply, intent, end_call).
    """

    # conversation history for this user
    history = conversation_history[user_id]

    # high-level dialog act: confirm / reject / end_call
    dialog_act = detect_confirmation_or_end(message, history)

    user = banking.get_user(db, user_id)
    account = banking.get_account_for_user(db, user_id)

    # ---------- PENDING TRANSFER CONFIRMATION FLOW ----------
    if user_id in pending_transfers:
        pending = pending_transfers[user_id]

        print(
            f"[PENDING] dialog_act={dialog_act}, "
            f"pending_stage={pending.confirmation_stage}, "
            f"amount={pending.amount}, recipient={pending.recipient_name!r}"
        )

        # user clearly wants to end the call while transfer is pending
        if dialog_act == "end_call":
            # safety: DO NOT execute transfer
            del pending_transfers[user_id]
            reply = (
                "Okay, I will not make this transfer. "
                "Thank you for using our banking assistant. Goodbye."
            )
            return store_history(user_id, message, reply), "make_transfer", True

        # user clearly confirms
        if dialog_act == "confirm":
            if pending.confirmation_stage == 1:
                # go to final confirmation
                pending.confirmation_stage = 2
                amount_text = format_amount_pln(pending.amount)
                reply = (
                    f"I will execute a transfer of {amount_text} to "
                    f"{pending.recipient_name} with title '{pending.title}'. "
                    "Do you finally confirm this transfer?"
                )
                print(f"[PENDING] Moved to stage 2, reply={reply!r}")
                return store_history(user_id, message, reply), "make_transfer", False

            if pending.confirmation_stage == 2:
                # perform transfer now
                try:
                    banking.perform_transfer(
                        db,
                        user_id=pending.user_id,
                        amount=pending.amount,
                        recipient_name=pending.recipient_name,
                        recipient_iban=pending.recipient_iban,
                        title=pending.title,
                    )
                except ValueError as e:
                    reply = str(e)
                    del pending_transfers[user_id]
                    print(f"[PENDING] perform_transfer error: {reply}")
                    return (
                        store_history(user_id, message, reply),
                        "make_transfer",
                        False,
                    )

                amount_text = format_amount_pln(pending.amount)
                reply = (
                    f"Your transfer of {amount_text} to {pending.recipient_name} "
                    "has been ordered. I have sent you an SMS with confirmation. "
                    "You can cancel this transfer within twenty minutes by "
                    "contacting the bank. Is there anything else I can help you with?"
                )
                print(f"[PENDING] Transfer executed, reply={reply!r}")
                del pending_transfers[user_id]
                return store_history(user_id, message, reply), "make_transfer", False

        # user clearly rejects
        if dialog_act == "reject":
            del pending_transfers[user_id]
            reply = (
                "Okay, I will not make this transfer. "
                "What else would you like to do?"
            )
            print("[PENDING] Transfer rejected by user")
            return store_history(user_id, message, reply), "make_transfer", False

        # neither confirm nor reject nor end_call → ask again (model was unsure)
        reply = (
            "Please clearly confirm if you want to make this transfer, "
            "or say that you do not want it."
        )
        print("[PENDING] Unclear confirmation, asking again")
        return store_history(user_id, message, reply), "make_transfer", False

    # ---------- INTENT DETECTION (with history) ----------
    intent = detect_intent(message, history)
    print(f"[INTENT] message={message!r}, intent={intent!r}, dialog_act={dialog_act!r}")

    # ---------- INTENT: MAKE TRANSFER ----------
    if intent == "make_transfer":
        if account is None:
            reply = "I couldn't find an account for this user."
            print("[MAKE_TRANSFER] No account for user")
            return store_history(user_id, message, reply), intent, False

        print(f"[MAKE_TRANSFER] user_id={user_id}, message={message!r}")

        # 1. Recipient
        recipient_label = extract_recipient(message, history)
        print(f"[MAKE_TRANSFER] extracted recipient_label={recipient_label!r}")

        if not recipient_label:
            reply = "I didn't understand who the transfer should be sent to. "
            print("[MAKE_TRANSFER] No recipient detected")
            return store_history(user_id, message, reply), intent, False

        contact = banking.resolve_contact(db, user_id, recipient_label)
        print(
            f"[MAKE_TRANSFER] resolved contact="
            f"{contact.full_name if contact else None!r}"
        )

        if not contact:
            reply = (
                f"I don't know the recipient '{recipient_label}'. "
                "Please add them as a saved contact in your banking app."
            )
            print("[MAKE_TRANSFER] Contact not resolved")
            return store_history(user_id, message, reply), intent, False

        recipient_name = contact.full_name
        recipient_iban = contact.iban
        title = contact.default_title or f"Transfer to {contact.full_name}"
        pretty_label = f"{contact.full_name} ({contact.nickname})"

        # 2. Amount
        amount = extract_amount(message)
        used_last_amount = False
        last_title = title

        print(f"[MAKE_TRANSFER] initial parsed amount={amount}")

        # if no amount → check if user refers to "same amount as last time"
        if amount is None or amount <= 0:
            print(
                "[MAKE_TRANSFER] No valid amount detected, "
                "checking 'same amount as last time'..."
            )
            same_amt = refers_to_same_amount_as_last_time(message, history)
            print(f"[MAKE_TRANSFER] refers_to_same_amount_as_last_time={same_amt}")
            if same_amt:
                last_tx = banking.get_last_transfer_to_contact(
                    db, user_id, recipient_name
                )
                print(f"[MAKE_TRANSFER] last_tx for {recipient_name!r} = {last_tx}")
                if last_tx:
                    amount = last_tx.amount
                    used_last_amount = True
                    last_title = last_tx.title

        print(
            f"[MAKE_TRANSFER] final amount={amount}, "
            f"used_last_amount={used_last_amount}"
        )

        # still no sensible amount → ask user
        if amount is None or amount <= 0:
            reply = "I understand you want to make a transfer, but I couldn't detect the amount. "
            print("[MAKE_TRANSFER] Still no valid amount, asking user again")
            return store_history(user_id, message, reply), intent, False

        # 3. Do NOT execute transfer yet – create pending transfer and ask for confirmation
        pending = PendingTransfer(
            user_id=user_id,
            amount=amount,
            recipient_name=recipient_name,
            recipient_iban=recipient_iban,
            title=title,
            currency=account.currency,
            confirmation_stage=1,
        )
        pending_transfers[user_id] = pending

        amount_text = format_amount_pln(amount)

        if used_last_amount:
            reply = (
                f"Last time you paid {amount_text} to {recipient_name} "
                f"for '{last_title}'. Do you confirm repeating this transfer?"
            )
        else:
            reply = (
                f"You want to transfer {amount_text} to {pretty_label} "
                f"with title '{title}'. Do you confirm?"
            )

        print(f"[MAKE_TRANSFER] reply={reply!r}")
        return store_history(user_id, message, reply), intent, False

    # ---------- INTENT: CHECK BALANCE ----------
    if intent == "check_balance":
        if account is None:
            reply = "I couldn't find an account for this user."
            print("[CHECK_BALANCE] No account for user")
        else:
            reply = f"Your current balance is {account.balance:.2f} {account.currency} "
            print(f"[CHECK_BALANCE] reply={reply!r}")

        # user also clearly ends the call in same sentence
        if dialog_act == "end_call":
            reply = reply + " Thank you for using our banking assistant. Goodbye."
            print("[CHECK_BALANCE] end_call in same utterance")
            return store_history(user_id, message, reply), intent, True

        return store_history(user_id, message, reply), intent, False

    # ---------- INTENT: SHOW HISTORY ----------
    if intent == "show_history":
        # how many last transfers? (default 3)
        limit = extract_history_limit(message, default=3, max_limit=10)
        print(f"[SHOW_HISTORY] limit={limit}")
        transactions = banking.get_transactions_for_user(db, user_id, limit=limit)

        if not transactions:
            reply = "I couldn't find any transfers in your history."
            print("[SHOW_HISTORY] No transactions found")
            if dialog_act == "end_call":
                reply = reply + " Thank you for using our banking assistant. Goodbye."
                return store_history(user_id, message, reply), intent, True
            return store_history(user_id, message, reply), intent, False

        lines: List[str] = []
        for t in transactions:
            amount_text = format_amount_pln(t.amount)
            lines.append(
                f"Transfer of {amount_text} to {t.recipient_name}, title: {t.title}"
            )

        reply = "Here are your recent transfers:\n" + "\n".join(lines)
        print(f"[SHOW_HISTORY] reply={reply!r}")

        if dialog_act == "end_call":
            reply = reply + "\nThank you for using our banking assistant. Goodbye."
            print("[SHOW_HISTORY] end_call in same utterance")
            return store_history(user_id, message, reply), intent, True

        return store_history(user_id, message, reply), intent, False

    # ---------- OTHER QUESTIONS → LLM ----------
    # if user just closes the conversation ('thank you, that's all'),
    # we don't need to call LLM – just say goodbye
    if dialog_act == "end_call":
        reply = "Thank you for using our banking assistant. Goodbye."
        print("[OTHER] end_call without banking intent")
        return store_history(user_id, message, reply), "other", True

    context = ""
    if user:
        context += f"User: {user.name}\n"
    if account:
        context += f"Balance: {account.balance:.2f} {account.currency} "

    print(f"[OTHER] Falling back to LLM, context={context!r}")
    reply = ask_llm(message, context)
    print(f"[OTHER] LLM reply={reply!r}")
    return store_history(user_id, message, reply), intent, False
