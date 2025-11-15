# app/api/twilio.py
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
    if not (
        TWILIO_ACCOUNT_SID and TWILIO_API_KEY and TWILIO_API_SECRET and TWIML_APP_SID
    ):
        return JSONResponse(
            status_code=500,
            content={"error": "Missing Twilio configuration."},
        )

    token = AccessToken(
        TWILIO_ACCOUNT_SID,
        TWILIO_API_KEY,
        TWILIO_API_SECRET,
        identity="voice_user",
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

    resp = VoiceResponse()

    # ---------------------------------------------------
    # FIRST INTERACTION → ask for full name
    # ---------------------------------------------------
    if not SpeechResult:
        gather = Gather(
            input="speech",
            language="en-US",
            action="/twilio/voice",
            method="POST",
        )
        gather.say(
            "Welcome to the banking assistant. "
            "To begin, please say your full name.",
            language="en-US",
        )
        resp.append(gather)

        resp.say("No response detected. Goodbye.", language="en-US")
        return Response(content=str(resp), media_type="application/xml")

    # ---------------------------------------------------
    # WE RECEIVED USER SPEECH
    # ---------------------------------------------------
    print("USER SAID:", SpeechResult)

    reply, intent = process_message(SpeechResult, BACKEND_USER_ID, db)
    print("BACKEND:", reply, "| INTENT:", intent)

    # ---------------------------------------------------
    # AUTH FAILED → END CALL
    # ---------------------------------------------------
    if intent == "auth_failed":
        resp.say(reply, language="en-US")
        resp.hangup()
        return Response(content=str(resp), media_type="application/xml")

    # ---------------------------------------------------
    # NEED NEXT AUTH STEP
    # ---------------------------------------------------
    if intent == "auth_continue":
        gather = Gather(
            input="speech",
            language="en-US",
            action="/twilio/voice",
            method="POST",
        )
        gather.say(reply, language="en-US")
        resp.append(gather)
        return Response(content=str(resp), media_type="application/xml")

    # ---------------------------------------------------
    # AUTH SUCCESS → CONTINUE NORMAL DIALOG
    # ---------------------------------------------------
    if intent == "auth_success":
        gather = Gather(
            input="speech",
            language="en-US",
            action="/twilio/voice",
            method="POST",
        )
        gather.say(reply, language="en-US")  # “Authentication successful.”
        gather.say("How can I assist you?", language="en-US")
        resp.append(gather)
        return Response(content=str(resp), media_type="application/xml")

    # ---------------------------------------------------
    # NORMAL BANKING OPERATIONS
    # ---------------------------------------------------
    resp.say(reply, language="en-US")

    gather = Gather(
        input="speech",
        language="en-US",
        action="/twilio/voice",
        method="POST",
    )
    gather.say("You may ask another question.", language="en-US")
    resp.append(gather)

    return Response(content=str(resp), media_type="application/xml")
