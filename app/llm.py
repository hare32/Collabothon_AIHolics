from groq import Groq
from .config import GROQ_API_KEY

if not GROQ_API_KEY:
    raise RuntimeError("Brak GROQ_API_KEY w .env – ustaw go przed uruchomieniem.")

client = Groq(api_key=GROQ_API_KEY)

DEFAULT_MODEL = "llama-3.1-8b-instant"


def detect_intent(message: str) -> str:
    msg = message.lower()
    if "saldo" in msg or "stan konta" in msg:
        return "check_balance"
    if "przelew" in msg or "przelać" in msg:
        return "make_transfer"
    return "other"


def ask_llm(message: str, context: str) -> str:
    """
    Woła Groq Chat Completions (llama3-8b-8192) i zwraca odpowiedź asystenta.
    """
    prompt = (
        "Jesteś wirtualnym asystentem bankowym. "
        "Odpowiadasz krótko, jasno, po polsku.\n\n"
        f"Kontekst klienta:\n{context}\n\n"
        f"Pytanie klienta: {message}\n"
    )

    completion = client.chat.completions.create(
        model=DEFAULT_MODEL,
        messages=[
            {
                "role": "system",
                "content": "Jesteś asystentem bankowym mówiącym po polsku.",
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
    )

    # Groq SDK ma takie samo API jak OpenAI – message.content
    return completion.choices[0].message.content.strip()
