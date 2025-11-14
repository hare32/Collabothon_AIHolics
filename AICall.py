import os
from flask import Flask, jsonify, request
from twilio.jwt.access_token import AccessToken
from twilio.jwt.access_token.grants import VoiceGrant
from twilio.twiml.voice_response import VoiceResponse, Gather
from flask_cors import CORS
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)

ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
API_KEY = os.getenv("TWILIO_API_KEY")
API_SECRET = os.getenv("TWILIO_API_SECRET")
TWIML_APP_SID = os.getenv("TWIML_APP_SID")

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
groq_client = Groq(api_key=GROQ_API_KEY)


@app.route("/token")
def token():
    """Zwraca token do WebRTC w przeglądarce."""
    token = AccessToken(ACCOUNT_SID, API_KEY, API_SECRET, identity="browser_user")

    voice_grant = VoiceGrant(outgoing_application_sid=TWIML_APP_SID)
    token.add_grant(voice_grant)

    return jsonify({'token': token.to_jwt()})


def ask_ai(user_text: str) -> str:
    """Wysyła tekst do Groq i zwraca odpowiedź."""
    completion = groq_client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {
                "role": "system",
                "content": (
                    "Jesteś pomocnym asystentem głosowym. "
                    "Mówisz naturalnie po polsku, krótko i konkretnie."
                )
            },
            {"role": "user", "content": user_text},
        ],
        max_tokens=256,
    )

    return completion.choices[0].message.content.strip()


@app.route("/voice", methods=["POST"])
def voice():
    """Webhook Twilio Voice."""
    speech_result = request.values.get("SpeechResult")
    resp = VoiceResponse()

    if not speech_result:
        gather = Gather(
            input="speech",
            language="pl-PL",
            action="/voice",
            method="POST",
            speech_timeout="auto"
        )
        gather.say(
            "Cześć, jestem Twoim asystentem AI. Powiedz, o czym chcesz porozmawiać.",
            language="pl-PL"
        )
        resp.append(gather)

        resp.say("Nie usłyszałem nic. Rozłączam się.", language="pl-PL")
        return str(resp)

    print("USER SAID:", speech_result)

    ai_answer = ask_ai(speech_result)
    print("AI ANSWER:", ai_answer)

    resp.say(ai_answer, language="pl-PL")

    gather = Gather(
        input="speech",
        language="pl-PL",
        action="/voice",
        method="POST",
        speech_timeout="auto"
    )
    gather.say("Możesz zadać kolejne pytanie.", language="pl-PL")
    resp.append(gather)

    return str(resp)


if __name__ == "__main__":
    print("Flask startuje na porcie 5000")
    app.run(host="127.0.0.1", port=5000)
