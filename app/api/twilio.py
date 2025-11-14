from typing import Optional

from fastapi import APIRouter, Depends, Form
from fastapi.responses import Response, JSONResponse
from sqlalchemy.orm import Session

from twilio.jwt.access_token import AccessToken
from twilio.jwt.access_token.grants import VoiceGrant
from twilio.twiml.voice_response import VoiceResponse, Gather

from ..db import get_db
from ..assistant import process_message
from ..config import (
    TWILIO_ACCOUNT_SID,
    TWILIO_API_KEY,
    TWILIO_API_SECRET,
    TWIML_APP_SID,
    BACKEND_USER_ID,
)

router = APIRouter(prefix="/twilio", tags=["twilio"])


@router.get("/token")
def twilio_token():
    """
    Token do Twilio Voice SDK (WebRTC w przeglądarce).
    """
    if not (
        TWILIO_ACCOUNT_SID and TWILIO_API_KEY and TWILIO_API_SECRET and TWIML_APP_SID
    ):
        return JSONResponse(
            status_code=500,
            content={"error": "Brak konfiguracji Twilio w zmiennych środowiskowych."},
        )

    token = AccessToken(
        TWILIO_ACCOUNT_SID, TWILIO_API_KEY, TWILIO_API_SECRET, identity="browser_user"
    )
    voice_grant = VoiceGrant(outgoing_application_sid=TWIML_APP_SID)
    token.add_grant(voice_grant)

    jwt_token = token.to_jwt()
    if isinstance(jwt_token, bytes):
        jwt_token = jwt_token.decode("utf-8")

    return {"token": jwt_token}


@router.post("/voice")
def twilio_voice(
    SpeechResult: Optional[str] = Form(default=None),
    db: Session = Depends(get_db),
):
    """
    Webhook Twilio Voice – rozmowa telefoniczna z asystentem bankowym.
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
