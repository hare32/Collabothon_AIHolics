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

auth = VoiceAuthenticator()


@router.post("/voice")
def auth_voice(
    SpeechResult: Optional[str] = Form(default=None),
    db: Session = Depends(get_db),
):
    user_id = BACKEND_USER_ID
    user = get_user(db, user_id)

    resp = VoiceResponse()

    # FIRST ENTRY
    if not SpeechResult:
        auth.reset(user_id)
        gather = Gather(
            input="speech",
            language="en-US",
            action="/auth/voice",
            method="POST",
        )
        gather.say("Welcome. Please say your full name to begin.")
        resp.append(gather)
        resp.say("No speech detected. Goodbye.")
        return Response(content=str(resp), media_type="application/xml")

    # Normal authentication step → call logic class
    response_obj = auth.handle(user_id, SpeechResult, user)
    return Response(content=str(response_obj), media_type="application/xml")
