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
    - reusable by /twilio/voice endpoint
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
        print(f"[AUTH] reset() user_id={user_id}")
        self.auth_step[user_id] = 0
        self.auth_attempts[user_id] = 0

    # ------------------------------------------
    # Main handler for each voice message
    # ------------------------------------------
    def handle(self, user_id: str, message: str, user) -> VoiceResponse:
        """
        Processes one voice input and returns a Twilio VoiceResponse.
        """
        raw = message or ""
        msg = raw.lower().replace(" ", "")
        # tylko cyfry z wypowiedzi – ważne dla ID i PIN
        digits = "".join(ch for ch in raw if ch.isdigit())
        step = self.auth_step[user_id]

        print(
            f"[AUTH] handle() user_id={user_id} step={step} "
            f"raw_message={raw!r} normalized={msg!r} digits={digits!r} "
            f"attempts={self.auth_attempts[user_id]}"
        )

        resp = VoiceResponse()

        # ============================================================
        # STEP 0 — VERIFY FULL NAME
        # ============================================================
        if step == 0:
            expected = user.name.lower().replace(" ", "")
            print(f"[AUTH][STEP0] expected_name={expected!r}")

            if expected in msg:
                # OK
                print("[AUTH][STEP0] name matched -> moving to STEP 1")
                self.auth_step[user_id] = 1
                self.auth_attempts[user_id] = 0

                gather = self._gather("/twilio/voice")
                gather.say(
                    "Name confirmed. Please say the last four digits of your ID."
                )
                resp.append(gather)
                return resp

            # WRONG INPUT
            print("[AUTH][STEP0] name did NOT match -> retry")
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
            print(
                f"[AUTH][STEP1] expected_last4={last4!r}, extracted_digits={digits!r}"
            )

            ok = False
            if digits:
                # jeśli user powiedział tylko 4 cyfry → porównujemy bezpośrednio
                if len(digits) == 4 and digits == last4:
                    ok = True
                # jeśli user powiedział cały PESEL → interesuje nas końcówka
                elif len(digits) > 4 and digits.endswith(last4):
                    ok = True

            if ok:
                print("[AUTH][STEP1] last4 matched -> moving to STEP 2")
                self.auth_step[user_id] = 2
                self.auth_attempts[user_id] = 0

                gather = self._gather("/twilio/voice")
                gather.say("ID digits confirmed. Now say your four-digit PIN.")
                resp.append(gather)
                return resp

            print("[AUTH][STEP1] last4 did NOT match -> retry")
            return self._retry(
                resp,
                user_id,
                "Those digits do not match our records. Please repeat the last four digits of your ID.",
            )

        # ============================================================
        # STEP 2 — VERIFY PIN
        # ============================================================
        if step == 2:
            expected_pin = user.pin_code
            print(
                f"[AUTH][STEP2] expected_pin={expected_pin!r}, "
                f"extracted_digits={digits!r}"
            )

            ok = False
            if digits:
                # najczęściej: user mówi dokładnie 4 cyfry PIN-u
                if digits == expected_pin:
                    ok = True
                # gdyby STT dołożyło coś z przodu, ale końcówka się zgadza
                elif digits.endswith(expected_pin):
                    ok = True

            if ok:
                # SUCCESS
                print("[AUTH][STEP2] PIN matched -> AUTH SUCCESS, step=3")
                self.auth_step[user_id] = 3
                self.auth_attempts[user_id] = 0

                resp.say("Authentication successful. Redirecting you now.")
                # Redirect back to /twilio/voice (this is our main webhook)
                resp.redirect("/twilio/voice")
                return resp

            print("[AUTH][STEP2] PIN did NOT match -> retry")
            return self._retry(
                resp, user_id, "Incorrect PIN. Please repeat your four-digit PIN."
            )

        # ============================================================
        # STEP 3 — Already authenticated
        # ============================================================
        print("[AUTH][STEP3] already authenticated -> redirect to /twilio/voice")
        resp.redirect("/twilio/voice")
        return resp

    # ------------------------------------------
    # Helper: create gather block
    # ------------------------------------------
    def _gather(self, action: str) -> Gather:
        print(f"[AUTH] _gather() action={action}")
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
        print(
            f"[AUTH] _retry() user_id={user_id} "
            f"attempts={self.auth_attempts[user_id]} step={self.auth_step[user_id]}"
        )

        # Too many attempts
        if self.auth_attempts[user_id] >= 3:
            print("[AUTH] too many attempts -> hangup + reset()")
            resp.say("Authentication failed. Ending the session for your security.")
            resp.hangup()
            self.reset(user_id)
            return resp

        # Try again
        gather = self._gather("/twilio/voice")
        gather.say(message)
        resp.append(gather)
        return resp
