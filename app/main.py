import os
import re
from typing import Optional, Tuple

from fastapi import FastAPI, Depends, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, JSONResponse
from sqlalchemy.orm import Session

from twilio.jwt.access_token import AccessToken
from twilio.jwt.access_token.grants import VoiceGrant
from twilio.twiml.voice_response import VoiceResponse, Gather

from .db import Base, engine, get_db
from . import banking
from .schemas import ChatRequest, ChatResponse
from .llm import detect_intent, ask_llm

# ---- DB init ----
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Collab Voice Assistant")

# ---- CORS (dla frontu z przeglądarki) ----
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # na demo może zostać *, do produkcji zawęź
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- Twilio config z env ----
ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
API_KEY = os.getenv("TWILIO_API_KEY")
API_SECRET = os.getenv("TWILIO_API_SECRET")
TWIML_APP_SID = os.getenv("TWIML_APP_SID")

# ID użytkownika w Twoim systemie (na razie na sztywno)
BACKEND_USER_ID = os.getenv("BACKEND_USER_ID", "user-1")


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
def startup() -> None:
    with next(get_db()) as db:
        banking.seed_data(db)


@app.get("/health")
def health():
    return {"status": "ok"}


# ---------- WSPÓLNA LOGIKA: PRZETWARZANIE WIADOMOŚCI ----------


def process_message(
    message: str, user_id: str, db: Session
) -> Tuple[str, Optional[str]]:
    """
    Wspólna logika asystenta:
    - intencje
    - przelew
    - saldo
    - fallback do LLM

    Zwraca (reply, intent).
    """
    intent = detect_intent(message)
    user = banking.get_user(db, user_id)
    account = banking.get_account_for_user(db, user_id)

    # ---------- INTENCJA: PRZELEW ----------
    if intent == "make_transfer":
        if account is None:
            return "Nie znaleziono konta dla tego użytkownika.", intent

        amount = extract_amount(message)
        if amount <= 0:
            return "Nie udało mi się rozpoznać poprawnej kwoty przelewu.", intent

        try:
            updated = banking.perform_transfer(db, user_id, amount)
        except ValueError as e:
            # np. niewystarczające środki
            return str(e), intent

        reply = (
            f"Przelew na kwotę {amount:.2f} {updated.currency} został wykonany. "
            f"Twoje aktualne saldo to {updated.balance:.2f} {updated.currency} "
            f"na koncie {updated.iban}."
        )
        return reply, intent

    # ---------- INTENCJA: SPRAWDZENIE SALDA ----------
    if intent == "check_balance":
        if account is None:
            reply = "Nie znaleziono konta dla tego użytkownika."
        else:
            reply = (
                f"Twoje aktualne saldo wynosi {account.balance:.2f} {account.currency} "
                f"na koncie {account.iban}."
            )
        return reply, intent

    # ---------- POZOSTAŁE PYTANIA → LLM ----------
    context = ""
    if user:
        context += f"Użytkownik: {user.name}\n"
    if account:
        context += (
            f"Saldo: {account.balance:.2f} {account.currency} "
            f"na koncie {account.iban}\n"
        )

    reply = ask_llm(message, context)
    return reply, intent


# ---------- HTTP CHAT (CLI / frontend tekstowy) ----------


@app.post("/assistant/chat", response_model=ChatResponse)
def assistant_chat(req: ChatRequest, db: Session = Depends(get_db)):
    reply, intent = process_message(req.message, req.user_id, db)
    return ChatResponse(reply=reply, intent=intent)


# ---------- TWILIO: TOKEN DLA PRZEGLĄDARKI ----------


@app.get("/twilio/token")
def twilio_token():
    """
    Zwraca token do WebRTC w przeglądarce (Twilio Voice SDK).
    Odpowiednik /token z AICall.py.
    """
    if not (ACCOUNT_SID and API_KEY and API_SECRET and TWIML_APP_SID):
        return JSONResponse(
            status_code=500,
            content={"error": "Brak konfiguracji Twilio w zmiennych środowiskowych."},
        )

    token = AccessToken(ACCOUNT_SID, API_KEY, API_SECRET, identity="browser_user")
    voice_grant = VoiceGrant(outgoing_application_sid=TWIML_APP_SID)
    token.add_grant(voice_grant)

    jwt_token = token.to_jwt()
    if isinstance(jwt_token, bytes):
        jwt_token = jwt_token.decode("utf-8")

    return {"token": jwt_token}


# ---------- TWILIO: WEBHOOK VOICE (TwiML) ----------


@app.post("/twilio/voice")
def twilio_voice(
    SpeechResult: Optional[str] = Form(default=None),
    db: Session = Depends(get_db),
):
    """
    Webhook Twilio Voice.
    Odpowiednik /voice z AICall.py, ale używa Twojego backendu (process_message)
    zamiast direct Groq.
    """
    resp = VoiceResponse()

    # Pierwsze wejście – brak rozpoznanego tekstu, prosimy o wypowiedź
    if not SpeechResult:
        gather = Gather(
            input="speech",
            language="pl-PL",
            action="/twilio/voice",
            method="POST",
            speech_timeout="auto",
        )
        gather.say(
            "Cześć, tu asystent bankowy. "
            "Możesz zapytać o saldo albo zlecić przelew.",
            language="pl-PL",
        )
        resp.append(gather)

        resp.say("Nie usłyszałem nic. Rozłączam się.", language="pl-PL")
        return Response(content=str(resp), media_type="application/xml")

    # Mamy tekst rozpoznany przez Twilio STT
    print("USER SAID:", SpeechResult)

    reply, intent = process_message(SpeechResult, BACKEND_USER_ID, db)
    print("BACKEND ANSWER:", reply, "| INTENT:", intent)

    # Odpowiedź głosowa
    resp.say(reply, language="pl-PL")

    # Kolejna runda rozmowy
    gather = Gather(
        input="speech",
        language="pl-PL",
        action="/twilio/voice",
        method="POST",
        speech_timeout="auto",
    )
    gather.say("Możesz zadać kolejne pytanie.", language="pl-PL")
    resp.append(gather)

    return Response(content=str(resp), media_type="application/xml")
