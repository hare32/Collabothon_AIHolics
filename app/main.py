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
    m = re.search(r"(\d+[,.]?\d*)", message.replace(" ", ""))
    if not m:
        return 0.0
    return float(m.group(1).replace(",", "."))


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

    transfer_info = ""

    # ---- LOGIKA PRZELEWU ----
    if intent == "make_transfer" and account:
        amount = extract_amount(req.message)

        if amount > 0:
            try:
                account = banking.perform_transfer(db, req.user_id, amount)
                transfer_info = f"Przelew wykonany: {amount:.2f} {account.currency}."
            except ValueError as e:
                transfer_info = str(e)
        else:
            transfer_info = "Nie udało się rozpoznać kwoty przelewu."

    # ---- KONTEKST ----
    context = ""
    if user:
        context += f"Użytkownik: {user.name}\n"
    if account:
        context += f"Saldo: {account.balance:.2f} {account.currency} na koncie {account.iban}\n"
    if transfer_info:
        context += f"{transfer_info}\n"

    reply = ask_llm(req.message, context)

    return ChatResponse(reply=reply, intent=intent)
