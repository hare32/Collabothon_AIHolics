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

Schemat JSON:
{"intent": "nazwa_intencji", "amount": 100.0, "reply": "Tekst, który bot ma powiedzieć klientowi"}

PRZYKŁADY:

User: "jaki mam stan konta"
Assistant: {"intent": "check_balance", "amount": null, "reply": "Pana saldo to [SALDO]"}

User: "chcę przelać 100 zł"
Assistant: {"intent": "make_transfer", "amount": 100.0, "reply": "OK, przelewam 100 zł. Pana nowe saldo to [SALDO]"}

User: "chcę przelać stówkę"
Assistant: {"intent": "make_transfer", "amount": 100.0, "reply": "OK, przelewam 100 zł. Pana nowe saldo to [SALDO]"}

User: "przelej dwie stówy i 50 groszy"
Assistant: {"intent": "make_transfer", "amount": 200.50, "reply": "OK, przelewam 200.50 zł. Pana nowe saldo to [SALDO]"}

User: "cześć"
Assistant: {"intent": "other", "amount": null, "reply": "Cześć, w czym mogę pomóc?"}
"""


def get_or_create_history(db: Session, user_id: str) -> list:
    """Pobiera historię z DB lub tworzy nową z promptem systemowym."""
    stmt = select(ChatHistory).where(ChatHistory.user_id == user_id)
    history_obj = db.execute(stmt).scalar_one_or_none()

    if history_obj is None or not history_obj.history_json:
        # Stwórz nową historię z promptem systemowym
        return [{"role": "system", "content": SYSTEM_PROMPT}]

    # Załaduj istniejącą historię z JSON string
    return json.loads(history_obj.history_json)


def save_history(db: Session, user_id: str, history: list):
    """Zapisuje zaktualizowaną historię z powrotem do DB jako JSON string."""
    stmt = select(ChatHistory).where(ChatHistory.user_id == user_id)
    history_obj = db.execute(stmt).scalar_one_or_none()

    # Konwertuj listę dict na string JSON
    history_str = json.dumps(history, ensure_ascii=False)

    if history_obj is None:
        history_obj = ChatHistory(user_id=user_id, history_json=history_str)
        db.add(history_obj)
    else:
        history_obj.history_json = history_str

    # Zapisz zmiany do bazy danych
    db.commit()


def get_contextual_response(db: Session, user_id: str, message: str) -> dict:
    """
    Główna funkcja MCP.
    Pobiera historię, dodaje nową wiadomość, pyta LLM, zapisuje historię.
    """

    # 1. Pobierz historię
    history = get_or_create_history(db, user_id)

    # 2. Dodaj nową wiadomość użytkownika
    history.append({"role": "user", "content": message})

    try:
        # 3. Wyślij *całą* historię do Groq
        completion = client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=history,
            response_format={"type": "json_object"},  # Zawsze proś o JSON!
            temperature=0.1  # Niska temperatura dla precyzyjnych JSON-ów
        )

        response_str = completion.choices[0].message.content or "{}"

        # 4. Zapisz odpowiedź AI (jako string JSON) w historii
        # To ważne, aby AI pamiętała, co sama "powiedziała"
        history.append({"role": "assistant", "content": response_str})

        # 5. Zapisz całą zaktualizowaną historię w DB
        save_history(db, user_id, history)

        # 6. Zwróć sparsowany JSON do main.py
        return json.loads(response_str)

    except Exception as e:
        print(f"[ERROR LLM MCP] {e}")
        return {
            "intent": "other",
            "amount": None,
            "reply": "Przepraszam, mam chwilowy problem z systemem AI."
        }