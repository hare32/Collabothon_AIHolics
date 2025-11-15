from collections import defaultdict
from twilio.twiml.voice_response import VoiceResponse, Gather


class VoiceAuthenticator:
    """
    Multi-step authentication flow:
      STEP 0 – verify name
      STEP 1 – verify last 4 digits of ID
      STEP 2 – verify 4-digit PIN
      STEP 3 – redirect to /twilio/voice
    """

    MAX_ATTEMPTS = 3

    def __init__(self):
        self.auth_step = defaultdict(int)
        self.attempts = defaultdict(int)

    def reset(self, user_id: str):
        print(f"[AUTH] Reset state for user={user_id}")
        self.auth_step[user_id] = 0
        self.attempts[user_id] = 0

    def handle(self, user_id: str, message: str, user) -> VoiceResponse:
        message = message or ""
        digits_all = "".join(ch for ch in message if ch.isdigit())
        digits = digits_all[-4:] if len(digits_all) >= 4 else digits_all
        cleaned = message.lower().replace(" ", "")
        step = self.auth_step[user_id]

        print(f"[AUTH] step={step}, digits='{digits}', msg='{cleaned}'")

        resp = VoiceResponse()

        if step == 0:
            return self._handle_name_step(resp, user_id, user, cleaned)

        if step == 1:
            return self._handle_id_step(resp, user_id, user, digits)

        if step == 2:
            return self._handle_pin_step(resp, user_id, user, digits)

        # Already authenticated
        resp.redirect("/twilio/voice")
        return resp

    # === Steps ===

    def _handle_name_step(self, resp, user_id, user, cleaned):
        if user.name.lower().replace(" ", "") in cleaned:
            print("[AUTH] NAME OK → STEP 1")
            self.auth_step[user_id] = 1
            return self._ask(
                resp,
                "/auth/voice",
                "Name confirmed. Please say the last four digits of your ID.",
            )
        return self._retry(
            resp,
            user_id,
            "I did not recognize that name. Please repeat your full name.",
        )

    def _handle_id_step(self, resp, user_id, user, digits):
        if digits == user.pesel[-4:]:
            print("[AUTH] LAST 4 OK → STEP 2")
            self.auth_step[user_id] = 2
            return self._ask(
                resp, "/auth/voice", "ID digits confirmed. Now say your four-digit PIN."
            )
        return self._retry(
            resp,
            user_id,
            "Those digits do not match our records. Please repeat the last four digits of your ID.",
        )

    def _handle_pin_step(self, resp, user_id, user, digits):
        if digits == user.pin_code:
            print("[AUTH] PIN OK → SUCCESS")
            self.auth_step[user_id] = 3
            resp.say("Authentication successful. Redirecting you now.")
            resp.redirect("/twilio/voice")
            return resp
        return self._retry(
            resp, user_id, "Incorrect PIN. Please repeat your four-digit PIN."
        )

    # === Helpers ===

    def _ask(self, resp: VoiceResponse, action: str, text: str) -> VoiceResponse:
        gather = self._gather(action)
        gather.say(text)
        resp.append(gather)
        return resp

    def _retry(self, resp: VoiceResponse, user_id: str, msg: str) -> VoiceResponse:
        self.attempts[user_id] += 1
        if self.attempts[user_id] >= self.MAX_ATTEMPTS:
            print("[AUTH] Too many attempts — hangup")
            resp.say("Authentication failed. Ending session for your security.")
            resp.hangup()
            self.reset(user_id)
            return resp
        return self._ask(resp, "/auth/voice", msg)

    def _gather(self, action: str) -> Gather:
        return Gather(
            input="speech",
            language="en-US",
            action=action,
            method="POST",
            speech_timeout="auto",
        )
