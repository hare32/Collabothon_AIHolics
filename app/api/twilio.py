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
    Generates a token for Twilio Voice SDK (WebRTC in the browser).
    """
    if not (
        TWILIO_ACCOUNT_SID and TWILIO_API_KEY and TWILIO_API_SECRET and TWIML_APP_SID
    ):
        return JSONResponse(
            status_code=500,
            content={"error": "Missing Twilio configuration in environment variables."},
        )

    token = AccessToken(
        TWILIO_ACCOUNT_SID,
        TWILIO_API_KEY,
        TWILIO_API_SECRET,
        identity="browser_user",
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
    Twilio Voice webhook — phone call conversation with the banking assistant.
    """
    resp = VoiceResponse()

    # First interaction — no speech recognized yet, ask user to speak
    if not SpeechResult:
        gather = Gather(
            input="speech",
            language="en-US",
            action="/twilio/voice",
            method="POST",
            speech_timeout="auto",
        )
        gather.say(
            "Hello, this is your banking assistant. "
            "You can ask about your balance or request a money transfer.",
            language="en-US",
        )
        resp.append(gather)

        resp.say("I didn't hear anything. Ending the call.", language="en-US")
        return Response(content=str(resp), media_type="application/xml")

    # We received speech recognized by Twilio STT
    print("USER SAID:", SpeechResult)

    reply, intent = process_message(SpeechResult, BACKEND_USER_ID, db)
    print("BACKEND ANSWER:", reply, "| INTENT:", intent)

    # Voice response with assistant's answer
    resp.say(reply, language="en-US")

    # Next round of conversation
    gather = Gather(
        input="speech",
        language="en-US",
        action="/twilio/voice",
        method="POST",
        speech_timeout="auto",
    )
    gather.say("You can ask another question.", language="en-US")
    resp.append(gather)

    return Response(content=str(resp), media_type="application/xml")
