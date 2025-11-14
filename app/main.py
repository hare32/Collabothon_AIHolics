import re
from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session

from .db import Base, engine, get_db
from . import banking
from .schemas import ChatRequest, ChatResponse
from .llm import detect_intent, ask_llm

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Collab Voice Assistant")


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


@app.on_event("startup")
def startup():
    with next(get_db()) as db:
        banking.seed_data(db)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/assistant/chat", response_model=ChatResponse)
def assistant_chat(req: ChatRequest, db: Session = Depends(get_db)):
    intent = detect_intent(req.message)
    user = banking.get_user(db, req.user_id)
    account = banking.get_account_for_user(db, req.user_id)

    # ---------- INTENCJA: PRZELEW ----------
    if intent == "make_transfer":
        if account is None:
            return ChatResponse(
                reply="Nie znaleziono konta dla tego użytkownika.",
                intent=intent,
            )

        amount = extract_amount(req.message)
        if amount <= 0:
            return ChatResponse(
                reply="Nie udało mi się rozpoznać poprawnej kwoty przelewu.",
                intent=intent,
            )

        try:
            updated = banking.perform_transfer(db, req.user_id, amount)
        except ValueError as e:
            # np. niewystarczające środki
            return ChatResponse(reply=str(e), intent=intent)

        reply = (
            f"Przelew na kwotę {amount:.2f} {updated.currency} został wykonany. "
            f"Twoje aktualne saldo to {updated.balance:.2f} {updated.currency} "
            f"na koncie {updated.iban}."
        )
        return ChatResponse(reply=reply, intent=intent)

    # ---------- INTENCJA: SPRAWDZENIE SALDA ----------
    if intent == "check_balance":
        if account is None:
            reply = "Nie znaleziono konta dla tego użytkownika."
        else:
            reply = (
                f"Twoje aktualne saldo wynosi {account.balance:.2f} {account.currency} "
                f"na koncie {account.iban}."
            )
        return ChatResponse(reply=reply, intent=intent)

    # ---------- POZOSTAŁE PYTANIA → LLM ----------
    context = ""
    if user:
        context += f"Użytkownik: {user.name}\n"
    if account:
        context += f"Saldo: {account.balance:.2f} {account.currency} na koncie {account.iban}\n"

    reply = ask_llm(req.message, context)
    return ChatResponse(reply=reply, intent=intent)
