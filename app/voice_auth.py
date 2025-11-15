from typing import Optional
from collections import defaultdict
from twilio.twiml.voice_response import VoiceResponse, Gather


class VoiceAuthenticator:
    """
    Voice-based multi-step authentication:
        STEP 0 → verify name
        STEP 1 → verify last 4 digits of ID
        STEP 2 → verify 4-digit PIN
        STEP 3 → success (redirect to /twilio/voice)
    """

    def __init__(self):
        self.auth_step = defaultdict(int)
        self.auth_attempts = defaultdict(int)

    def reset(self, user_id: str):
        print(f"[AUTH] reset state for user={user_id}")
        self.auth_step[user_id] = 0
        self.auth_attempts[user_id] = 0

    def handle(self, user_id: str, message: str, user) -> VoiceResponse:
        raw = message or ""

        # Extract digits properly (only last 4 digits count)
        digits_all = "".join(ch for ch in raw if ch.isdigit())
        digits = digits_all[-4:] if len(digits_all) >= 4 else digits_all

        msg_clean = raw.lower().replace(" ", "")
        step = self.auth_step[user_id]

        print(f"[AUTH] step={step}, digits='{digits}', msg='{msg_clean}'")

        resp = VoiceResponse()

        # STEP 0 — NAME
        if step == 0:
            expected = user.name.lower().replace(" ", "")
            if expected in msg_clean:
                print("[AUTH] NAME OK → STEP 1")
                self.auth_step[user_id] = 1
                return self._ask(
                    resp,
                    "/auth/voice",
                    "Name confirmed. Please say the last four digits of your ID.",
                )
            else:
                return self._retry(
                    resp,
                    user_id,
                    "I did not recognize that name. Please repeat your full name.",
                )

        # STEP 1 — LAST 4 OF PESEL/ID
        if step == 1:
            last4 = user.pesel[-4:]
            if digits == last4:
                print("[AUTH] LAST 4 OK → STEP 2")
                self.auth_step[user_id] = 2
                return self._ask(
                    resp,
                    "/auth/voice",
                    "ID digits confirmed. Now say your four-digit PIN.",
                )
            else:
                return self._retry(
                    resp,
                    user_id,
                    "Those digits do not match our records. Please repeat the last four digits of your ID.",
                )

        # STEP 2 — PIN
        if step == 2:
            pin = user.pin_code
            if digits == pin:
                print("[AUTH] PIN OK → SUCCESS")
                self.auth_step[user_id] = 3
                resp.say("Authentication successful. Redirecting you now.")
                resp.redirect("/twilio/voice")
                return resp
            else:
                return self._retry(
                    resp, user_id, "Incorrect PIN. Please repeat your four-digit PIN."
                )

        # Already authenticated
        print("[AUTH] already authenticated — redirect")
        resp.redirect("/twilio/voice")
        return resp

    # Helper methods
    def _ask(self, resp: VoiceResponse, action: str, text: str):
        gather = self._gather(action)
        gather.say(text)
        resp.append(gather)
        return resp

    def _retry(self, resp: VoiceResponse, user_id: str, msg: str):
        self.auth_attempts[user_id] += 1
        if self.auth_attempts[user_id] >= 3:
            print("[AUTH] too many attempts — hangup")
            resp.say("Authentication failed. Ending session for your security.")
            resp.hangup()
            self.reset(user_id)
            return resp

        return self._ask(resp, "/auth/voice", msg)

    def _gather(self, action: str):
        return Gather(
            input="speech",
            language="en-US",
            action=action,
            method="POST",
            speech_timeout="auto",
        )
