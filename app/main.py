from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session

from .db import Base, engine, get_db
from . import banking
from .schemas import ChatRequest, ChatResponse
from .llm import detect_intent, ask_llm

# Create database tables
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Collab Voice Assistant")


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

    context = ""
    if user:
        context += f"Użytkownik: {user.name}\n"
    if account:
        context += f"Saldo: {account.balance} {account.currency} na {account.iban}\n"

    reply = ask_llm(req.message, context)

    return ChatResponse(reply=reply, intent=intent)
