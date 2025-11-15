from typing import Optional
from fastapi import APIRouter, Depends, Form
from fastapi.responses import Response
from sqlalchemy.orm import Session
from twilio.twiml.voice_response import VoiceResponse, Gather

from ..db import get_db
from ..banking import get_user
from ..config import BACKEND_USER_ID
from ..voice_auth import VoiceAuthenticator

router = APIRouter(prefix="/auth", tags=["auth"])

authenticator = VoiceAuthenticator()


@router.post("/voice")
def auth_voice(
    SpeechResult: Optional[str] = Form(default=None),
    db: Session = Depends(get_db),
):
    """
    Twilio entry point for voice-based authentication.
    Flow:
      1. Ask for full name
      2. Ask for last 4 digits of ID
      3. Ask for PIN
      4. Redirect to /twilio/voice after success
    """
    user_id = BACKEND_USER_ID
    user = get_user(db, user_id)
    resp = VoiceResponse()

    # === First entry (no speech yet) ===
    if not SpeechResult:
        authenticator.reset(user_id)
        gather = Gather(
            input="speech",
            language="en-US",
            action="/auth/voice",
            method="POST",
            speech_timeout="auto",
        )
        gather.say("Welcome. Please say your full name to begin.")
        resp.append(gather)
        resp.say("No speech detected. Goodbye.")
        return Response(content=str(resp), media_type="application/xml")

    # === Continue authentication ===
    response_obj = authenticator.handle(user_id, SpeechResult, user)
    return Response(content=str(response_obj), media_type="application/xml")
