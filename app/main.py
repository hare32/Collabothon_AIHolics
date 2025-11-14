import os
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
from .llm import get_contextual_response

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Collab Voice Assistant")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
API_KEY = os.getenv("TWILIO_API_KEY")
API_SECRET = os.getenv("TWILIO_API_SECRET")
TWIML_APP_SID = os.getenv("TWIML_APP_SID")
BACKEND_USER_ID = os.getenv("BACKEND_USER_ID", "user-1")

@app.on_event("startup")
def startup() -> None:
    with next(get_db()) as db:
        banking.seed_data(db)


@app.get("/health")
def health():
    return {"status": "ok"}



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
        account = banking.get_account_for_user(db, user_id)
        if account is None:
            return "Nie znaleziono konta dla tego użytkownika.", intent

        amount = llm_resp.get("amount")
        if not isinstance(amount, (int, float)) or amount <= 0:
            pass
        else:
            try:
                updated = banking.perform_transfer(db, user_id, amount)
                final_reply = reply_template.replace(
                    "[SALDO]", f"{updated.balance:.2f} {updated.currency}"
                )
            except ValueError as e:
                # np. niewystarczające środki
                return str(e), intent

    # ---------- INTENCJA: SPRAWDZENIE SALDA ----------
    elif intent == "check_balance":
        account = banking.get_account_for_user(db, user_id)
        if account is None:
            final_reply = "Nie znaleziono konta dla tego użytkownika."
        else:
            final_reply = reply_template.replace(
                "[SALDO]", f"{account.balance:.2f} {account.currency}"
            )

    return final_reply, intent


@app.post("/assistant/chat", response_model=ChatResponse)
def assistant_chat(req: ChatRequest, db: Session = Depends(get_db)):
    reply, intent = process_message(req.message, req.user_id, db)
    return ChatResponse(reply=reply, intent=intent)

@app.get("/twilio/token")
def twilio_token():
    """
    Zwraca token do WebRTC w przeglądarce (Twilio Voice SDK).
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

@app.post("/twilio/voice")
def twilio_voice(
        SpeechResult: Optional[str] = Form(default=None),
        db: Session = Depends(get_db),
):
    """
    Webhook Twilio Voice.
    """
    resp = VoiceResponse()

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