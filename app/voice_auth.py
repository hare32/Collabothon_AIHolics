from typing import Optional
from collections import defaultdict

from twilio.twiml.voice_response import VoiceResponse, Gather


class VoiceAuthenticator:
    """
    Full voice authentication flow:
        STEP 0 → name
        STEP 1 → last 4 digits of PESEL
        STEP 2 → PIN
        STEP 3 → authenticated (redirect to banking)

    - 3 attempts per step
    - resets session after failure
    - reusable by /auth/voice endpoint
    """

    def __init__(self):
        # Per-user step
        self.auth_step = defaultdict(int)
        # Per-user attempts per step
        self.auth_attempts = defaultdict(int)

    # ------------------------------------------
    # Reset state
    # ------------------------------------------
    def reset(self, user_id: str):
        self.auth_step[user_id] = 0
        self.auth_attempts[user_id] = 0

    # ------------------------------------------
    # Main handler for each voice message
    # ------------------------------------------
    def handle(self, user_id: str, message: str, user) -> VoiceResponse:
        """
        Processes one voice input and returns a Twilio VoiceResponse.
        """
        msg = message.lower().replace(" ", "")
        step = self.auth_step[user_id]

        resp = VoiceResponse()

        # ============================================================
        # STEP 0 — VERIFY FULL NAME
        # ============================================================
        if step == 0:
            expected = user.name.lower().replace(" ", "")

            if expected in msg:
                # OK
                self.auth_step[user_id] = 1
                self.auth_attempts[user_id] = 0

                gather = self._gather("/auth/voice")
                gather.say(
                    "Name confirmed. Please say the last four digits of your ID."
                )
                resp.append(gather)
                return resp

            # WRONG INPUT
            return self._retry(
                resp,
                user_id,
                "I did not recognize that name. Please repeat your full name.",
            )

        # ============================================================
        # STEP 1 — VERIFY LAST 4 OF PESEL
        # ============================================================
        if step == 1:
            last4 = user.pesel[-4:]

            if last4 in msg:
                self.auth_step[user_id] = 2
                self.auth_attempts[user_id] = 0

                gather = self._gather("/auth/voice")
                gather.say("ID digits confirmed. Now say your four-digit PIN.")
                resp.append(gather)
                return resp

            return self._retry(
                resp,
                user_id,
                "Those digits do not match our records. Please repeat the last four digits of your ID.",
            )

        # ============================================================
        # STEP 2 — VERIFY PIN
        # ============================================================
        if step == 2:
            if user.pin_code in msg:
                # SUCCESS
                self.auth_step[user_id] = 3
                self.auth_attempts[user_id] = 0

                resp.say("Authentication successful. Redirecting you now.")
                resp.redirect("/twilio/voice")
                return resp

            return self._retry(
                resp, user_id, "Incorrect PIN. Please repeat your four-digit PIN."
            )

        # ============================================================
        # STEP 3 — Already authenticated
        # ============================================================
        resp.redirect("/twilio/voice")
        return resp

    # ------------------------------------------
    # Helper: create gather block
    # ------------------------------------------
    def _gather(self, action: str) -> Gather:
        return Gather(
            input="speech",
            language="en-US",
            action=action,
            method="POST",
            speech_timeout="auto",
        )

    # ------------------------------------------
    # Helper: retry with attempt check
    # ------------------------------------------
    def _retry(self, resp: VoiceResponse, user_id: str, message: str):
        self.auth_attempts[user_id] += 1

        # Too many attempts
        if self.auth_attempts[user_id] >= 3:
            resp.say("Authentication failed. Ending the session for your security.")
            resp.hangup()
            self.reset(user_id)
            return resp

        # Try again
        gather = self._gather("/auth/voice")
        gather.say(message)
        resp.append(gather)
        return resp
