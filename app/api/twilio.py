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
from ..banking import get_user

router = APIRouter(prefix="/twilio", tags=["twilio"])


@router.get("/token")
def twilio_token():
    """Returns a Twilio Voice SDK token for browser calls."""
    if not all([TWILIO_ACCOUNT_SID, TWILIO_API_KEY, TWILIO_API_SECRET, TWIML_APP_SID]):
        return JSONResponse(
            status_code=500,
            content={"error": "Missing Twilio configuration."},
        )

    token = AccessToken(
        TWILIO_ACCOUNT_SID,
        TWILIO_API_KEY,
        TWILIO_API_SECRET,
        identity="web_user",
    )
    token.add_grant(VoiceGrant(outgoing_application_sid=TWIML_APP_SID))

    jwt = token.to_jwt()
    if isinstance(jwt, bytes):
        jwt = jwt.decode()

    return {"token": jwt}


@router.post("/voice")
def twilio_voice(
    SpeechResult: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    """Main post-auth banking conversational endpoint."""
    user_id = BACKEND_USER_ID
    user = get_user(db, user_id)

    resp = VoiceResponse()

    if not user:
        resp.say("System error: user not found.")
        resp.hangup()
        return Response(str(resp), media_type="application/xml")

    # First entry → greet user
    if not SpeechResult:
        gather = Gather(
            input="speech",
            language="en-US",
            action="/twilio/voice",
            method="POST",
            speech_timeout="auto",
        )
        gather.say("Hi, I am your banking assistant. How can I help you today?")
        resp.append(gather)
        resp.say("I didn't hear anything. Goodbye.")
        return Response(str(resp), media_type="application/xml")

    # Process conversation
    reply, intent = process_message(SpeechResult, user_id, db)
    resp.say(reply)

    # Wait for next user message
    gather = Gather(
        input="speech",
        language="en-US",
        action="/twilio/voice",
        method="POST",
        speech_timeout="auto",
    )
    gather.say("You can ask another question.")
    resp.append(gather)

    return Response(str(resp), media_type="application/xml")
