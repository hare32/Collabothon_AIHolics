from typing import Optional, Dict, Any
import httpx

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

AUTH_STATE: Dict[str, Dict[str, Any]] = {}
AUTH_USER_ID = "user-1"
AUTH_SERVICE_URL = "http://localhost:9000/auth/verify"

@router.get("/token")
def twilio_token():
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
async def twilio_voice(
    CallSid: str = Form(...),
    SpeechResult: Optional[str] = Form(default=None),
    db: Session = Depends(get_db),
):
    resp = VoiceResponse()
    state = AUTH_STATE.get(CallSid)
    if state is None:
        AUTH_STATE[CallSid] = {
            "stage": "pesel",
            "answers": {},
            "authenticated": False,
        }

        gather = Gather(
            input="speech",
            language="en-US",
            action="/twilio/voice",
            method="POST",
            speech_timeout="auto",
        )
        gather.say(
            "Welcome to the bank. "
            "To verify your identity, please say the last four digits of your national ID number.",
        )
        resp.append(gather)
        return Response(content=str(resp), media_type="application/xml")

    if not state.get("authenticated", False):
        stage = state["stage"]

        if not SpeechResult:
            gather = Gather(
                input="speech",
                language="en-US",
                action="/twilio/voice",
                method="POST",
                speech_timeout="auto",
            )

            if stage == "pesel":
                gather.say(
                    "I didn't catch that. "
                    "Please say again the last four digits of your national ID number.",
                )
            elif stage == "telepin":
                gather.say(
                    "I didn't catch that. "
                    "Please say your phone PIN again, digit by digit.",
                )
            elif stage == "mother":
                gather.say(
                    "I didn't catch that. "
                    "Please say your mother's maiden name again.",
                )
            else:
                gather.say(
                    "I didn't catch that. Please say it again.",
                )

            resp.append(gather)
            return Response(content=str(resp), media_type="application/xml")

        if stage == "pesel":
            digits = "".join(ch for ch in (SpeechResult or "") if ch.isdigit())
            state["answers"]["pesel_last4"] = digits[-4:]
            state["stage"] = "telepin"

            gather = Gather(
                input="speech",
                language="en-US",
                action="/twilio/voice",
                method="POST",
                speech_timeout="auto",
            )
            gather.say(
                "Thank you. Now please say your phone PIN, digit by digit.",
            )
            resp.append(gather)
            return Response(content=str(resp), media_type="application/xml")

        if stage == "telepin":
            digits = "".join(ch for ch in (SpeechResult or "") if ch.isdigit())
            state["answers"]["telepin"] = digits
            state["stage"] = "mother"

            gather = Gather(
                input="speech",
                language="en-US",
                action="/twilio/voice",
                method="POST",
                speech_timeout="auto",
            )
            gather.say(
                "Finally, please say your mother's maiden name.",
            )
            resp.append(gather)
            return Response(content=str(resp), media_type="application/xml")

        if stage == "mother":
            state["answers"]["mother_maiden_name"] = (SpeechResult or "").strip()
            answers = state["answers"]

            async with httpx.AsyncClient() as client:
                verify_payload = {
                    "user_id": AUTH_USER_ID,
                    "pesel_last4": answers.get("pesel_last4", ""),
                    "telepin": answers.get("telepin", ""),
                    "mother_maiden_name": answers.get("mother_maiden_name", ""),
                }
                r = await client.post(AUTH_SERVICE_URL, json=verify_payload)

            if r.status_code != 200:
                resp.say(
                    "The details you provided do not match our records. "
                    "For your security, this call will be disconnected.",
                )
                AUTH_STATE.pop(CallSid, None)
                return Response(content=str(resp), media_type="application/xml")

            state["authenticated"] = True

            resp.say(
                "Thank you. Your identity has been successfully verified. "
                "I will now connect you to the banking assistant.",
            )

            gather = Gather(
                input="speech",
                language="en-US",
                action="/twilio/voice",
                method="POST",
                speech_timeout="auto",
            )
            gather.say(
                "Hi, I am your banking assistant. "
                "You can ask about your balance or request a money transfer.",
            )
            resp.append(gather)
            return Response(content=str(resp), media_type="application/xml")

    if not SpeechResult:
        gather = Gather(
            input="speech",
            language="en-US",
            action="/twilio/voice",
            method="POST",
            speech_timeout="auto",
        )
        gather.say(
            "Hi, I am your banking assistant. "
            "You can ask about your balance or request a money transfer.",
        )
        resp.append(gather)
        return Response(content=str(resp), media_type="application/xml")

    # We have recognized text from Twilio STT
    print("USER SAID:", SpeechResult)

    reply, intent = process_message(SpeechResult, BACKEND_USER_ID, db)
    print("BACKEND ANSWER:", reply, "| INTENT:", intent)

    resp.say(reply)

    gather = Gather(
        input="speech",
        language="en-US",
        action="/twilio/voice",
        method="POST",
        speech_timeout="auto",
    )
    gather.say("You can ask another question.")
    resp.append(gather)

    return Response(content=str(resp), media_type="application/xml")
