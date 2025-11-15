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
    Token for Twilio Voice SDK (browser WebRTC).
    """
    if not (
        TWILIO_ACCOUNT_SID and TWILIO_API_KEY and TWILIO_API_SECRET and TWIML_APP_SID
    ):
        return JSONResponse(
            status_code=500,
            content={"error": "Missing Twilio configuration in environment variables."},
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
    db: Session = Depends(get_db)
):
    resp = VoiceResponse()

    # Pierwsze wejście — pytamy o imię i nazwisko
    if not SpeechResult:
        gather = Gather(
            input="speech",
            language="en-US",
            action="/twilio/voice",
            method="POST",
            speech_timeout="auto",
        )
        gather.say("Welcome to your banking assistant. Please say your full name to begin.", language="en-US")
        resp.append(gather)

        resp.say("I didn't hear anything. Goodbye.", language="en-US")
        return Response(content=str(resp), media_type="application/xml")

    print("USER SAID:", SpeechResult)

    reply, intent = process_message(SpeechResult, BACKEND_USER_ID, db)
    print("BACKEND:", reply, "| INTENT:", intent)

    # Jeśli użytkownik ma kontynuować autentykację
    if intent == "auth_continue":
        gather = Gather(
            input="speech",
            language="en-US",
            action="/twilio/voice",
            method="POST",
            speech_timeout="auto",
        )
        gather.say(reply, language="en-US")
        resp.append(gather)
        return Response(content=str(resp), media_type="application/xml")

    # Autentykacja OK → przechodzimy do bankingu
    if intent == "auth_success":
        gather = Gather(
            input="speech",
            language="en-US",
            action="/twilio/voice",
            method="POST",
            speech_timeout="auto",
        )
        gather.say(reply, language="en-US")
        gather.say("How can I help you today?", language="en-US")
        resp.append(gather)
        return Response(content=str(resp), media_type="application/xml")

    # Normalna operacja bankowa
    resp.say(reply, language="en-US")

    gather = Gather(
        input="speech",
        language="en-US",
        action="/twilio/voice",
        method="POST",
        speech_timeout="auto",
    )
    gather.say("You may ask another question.", language="en-US")
    resp.append(gather)

    return Response(content=str(resp), media_type="application/xml")
