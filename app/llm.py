import json
from groq import Groq
from sqlalchemy.orm import Session
from sqlalchemy import select

from .config import GROQ_API_KEY
from .models import ChatHistory  # Nowy import

if not GROQ_API_KEY:
    raise RuntimeError("Brak GROQ_API_KEY w .env – ustaw go przed uruchomieniem.")

client = Groq(api_key=GROQ_API_KEY)

DEFAULT_MODEL = "llama-3.1-8b-instant"

SYSTEM_PROMPT = """
Jesteś asystentem bankowym AI. Twoim zadaniem jest przeanalizowanie rozmowy
z klientem i zwrócenie *tylko i wyłącznie* obiektu JSON.
Nigdy nie odpowiadasz potocznie. Zawsze zwracasz JSON.

Analizujesz całą historię rozmowy, aby zrozumieć kontekst.
Jeśli użytkownik mówi "przelej stówkę", a w następnym kroku "na ZUS",
musisz połączyć te fakty.

Dostępne intencje:
- "check_balance": Gdy użytkownik pyta o stan konta.
- "make_transfer": Gdy użytkownik chce przelać pieniądze. MUSISZ rozpoznać `amount`.
- "other": Wszystkie inne pytania (pogoda, powitania, itp.)

"""


def get_or_create_history(db: Session, user_id: str) -> list:
    stmt = select(ChatHistory).where(ChatHistory.user_id == user_id)
    history_obj = db.execute(stmt).scalar_one_or_none()

    if history_obj is None or not history_obj.history_json:
        return [{"role": "system", "content": SYSTEM_PROMPT}]

    return json.loads(history_obj.history_json)


def save_history(db: Session, user_id: str, history: list):
    stmt = select(ChatHistory).where(ChatHistory.user_id == user_id)
    history_obj = db.execute(stmt).scalar_one_or_none()

    history_str = json.dumps(history, ensure_ascii=False)

    if history_obj is None:
        history_obj = ChatHistory(user_id=user_id, history_json=history_str)
        db.add(history_obj)
    else:
        history_obj.history_json = history_str

    db.commit()


def get_contextual_response(db: Session, user_id: str, message: str) -> dict:
    history = get_or_create_history(db, user_id)

    history.append({"role": "user", "content": message})

    try:
        completion = client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=history,
            response_format={"type": "json_object"},
            temperature=0.1
        )

        response_str = completion.choices[0].message.content or "{}"

        history.append({"role": "assistant", "content": response_str})

        save_history(db, user_id, history)

        return json.loads(response_str)

    except Exception as e:
        print(f"[ERROR LLM MCP] {e}")
        return {
            "intent": "other",
            "amount": None,
            "reply": "Przepraszam, mam chwilowy problem z systemem AI."
        }