from typing import Optional
from collections import defaultdict

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
from ..voice_auth import VoiceAuthenticator

router = APIRouter(prefix="/twilio", tags=["twilio"])

# --- GLOBALNY STAN AUTENTYKACJI (in-memory, demo) ---
auth = VoiceAuthenticator()
authenticated_users = defaultdict(bool)  # user_id -> True/False


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
    db: Session = Depends(get_db),
):
    """
    Twilio Voice webhook – phone conversation with the banking assistant.
    Z wbudowaną autentykacją głosową.
    """
    user_id = BACKEND_USER_ID
    resp = VoiceResponse()
    user = get_user(db, user_id)

    # DEBUG: wejście do funkcji
    print(
        f"[TWILIO_VOICE] Incoming request: "
        f"SpeechResult={SpeechResult!r}, "
        f"authenticated={authenticated_users[user_id]}, "
        f"auth_step={auth.auth_step[user_id]}"
    )

    # ----------------------------------------------------
    # PIERWSZE WEJŚCIE (brak rozpoznanego tekstu z Twilio)
    # ----------------------------------------------------
    if not SpeechResult:
        # Jeśli użytkownik NIE jest jeszcze uwierzytelniony → zaczynamy flow auth
        if not authenticated_users[user_id]:
            print(
                "[TWILIO_VOICE] No SpeechResult & NOT authenticated -> start auth flow"
            )
            auth.reset(user_id)

            gather = Gather(
                input="speech",
                language="en-US",
                action="/twilio/voice",  # kolejne kroki auth wracają tu
                method="POST",
                speech_timeout="auto",
            )
            gather.say("Welcome. Please say your full name to begin.", language="en-US")
            resp.append(gather)

            resp.say("No speech detected. Goodbye.", language="en-US")

            xml = str(resp)
            print(f"[TWILIO_VOICE][AUTH-FIRST] TwiML response:\n{xml}")
            return Response(content=xml, media_type="application/xml")

        # Jeśli użytkownik JEST uwierzytelniony → stary bankingowy greeting
        print("[TWILIO_VOICE] No SpeechResult & authenticated -> banking greeting")
        gather = Gather(
            input="speech",
            language="en-US",
            action="/twilio/voice",
            method="POST",
            speech_timeout="auto",
        )
        gather.say(
            "Hi, this is your banking assistant. "
            "You can ask about your balance or request a transfer.",
            language="en-US",
        )
        resp.append(gather)

        resp.say("I didn't hear anything. Goodbye.", language="en-US")

        xml = str(resp)
        print(f"[TWILIO_VOICE][BANKING-FIRST] TwiML response:\n{xml}")
        return Response(content=xml, media_type="application/xml")

    # ----------------------------------------------------
    # MAMY rozpoznany tekst z Twilio STT
    # ----------------------------------------------------
    print("USER SAID:", SpeechResult)

    # ---------------------------------------------
    # 1) KROKI AUTENTYKACJI, jeśli jeszcze nie zalogowany
    # ---------------------------------------------
    if not authenticated_users[user_id]:
        print(
            f"[TWILIO_VOICE][AUTH] Before handle: "
            f"step={auth.auth_step[user_id]}, "
            f"attempts={auth.auth_attempts[user_id]}"
        )

        # Używamy istniejącej logiki VoiceAuthenticator
        auth_response = auth.handle(user_id, SpeechResult, user)

        print(
            f"[TWILIO_VOICE][AUTH] After handle: "
            f"step={auth.auth_step[user_id]}, "
            f"attempts={auth.auth_attempts[user_id]}"
        )

        # Jeżeli VoiceAuthenticator przeszedł do kroku 3 → sukces
        if auth.auth_step[user_id] == 3:
            authenticated_users[user_id] = True
            print(
                "[TWILIO_VOICE][AUTH] Authentication SUCCESS -> "
                "authenticated_users[user_id] = True"
            )

        xml = str(auth_response)
        print(f"[TWILIO_VOICE][AUTH] TwiML response (auth_response):\n{xml}")
        return Response(content=xml, media_type="application/xml")

    # ---------------------------------------------
    # 2) ZWYKŁA ROZMOWA BANKOWA (user już uwierzytelniony)
    # ---------------------------------------------
    print(
        f"[TWILIO_VOICE][BANKING] Authenticated user -> "
        f"calling assistant with SpeechResult={SpeechResult!r}"
    )
    reply, intent = process_message(SpeechResult, user_id, db)
    print("BACKEND ANSWER:", reply, "| INTENT:", intent)

    # Voice response
    resp.say(reply, language="en-US")

    # Next turn of the conversation
    gather = Gather(
        input="speech",
        language="en-US",
        action="/twilio/voice",
        method="POST",
        speech_timeout="auto",
    )
    gather.say("You can ask another question.", language="en-US")
    resp.append(gather)

    xml = str(resp)
    print(f"[TWILIO_VOICE][BANKING] TwiML response:\n{xml}")
    return Response(content=xml, media_type="application/xml")
