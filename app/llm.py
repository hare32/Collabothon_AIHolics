from groq import Groq
from .config import GROQ_API_KEY

if not GROQ_API_KEY:
    raise RuntimeError("Brak GROQ_API_KEY w .env – ustaw go przed uruchomieniem.")

client = Groq(api_key=GROQ_API_KEY)

DEFAULT_MODEL = "llama-3.1-8b-instant"


def detect_intent(message: str) -> str:
    """
    Wykrywa intencję użytkownika za pomocą LLM.
    Zwraca jeden z trzech stringów:
    - "make_transfer"  -> użytkownik chce zrobić przelew
    - "check_balance"  -> użytkownik chce sprawdzić saldo / stan konta
    - "other"          -> wszystko inne
    """

    system_prompt = (
        "Jesteś klasyfikatorem intencji w asystencie bankowym.\n"
        "Klient mówi po polsku. Na podstawie wypowiedzi klienta zwróć TYLKO jedno słowo:\n"
        "- make_transfer  jeśli chce wykonać przelew lub zapłacić komuś pieniądze\n"
        "- check_balance  jeśli pyta o saldo, stan konta, ile ma pieniędzy\n"
        "- other          jeśli wypowiedź nie dotyczy przelewu ani salda\n\n"
        "Przykłady:\n"
        "U: Daj sąsiadowi 50 zł\n"
        "A: make_transfer\n"
        "U: Zrób przelew dla sąsiada 50 zł\n"
        "A: make_transfer\n"
        "U: Ile mam pieniędzy?\n"
        "A: check_balance\n"
        "U: Jakie jest moje saldo?\n"
        "A: check_balance\n"
        "U: Opowiedz dowcip\n"
        "A: other\n"
        "Nie dodawaj żadnych wyjaśnień, komentarzy ani dodatkowego tekstu."
    )

    try:
        completion = client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message},
            ],
            temperature=0.0,
            max_tokens=5,
        )

        content = completion.choices[0].message.content or ""
        intent_raw = content.strip().lower()

        # prosta normalizacja, gdyby model odpisał np. z dużej litery
        mapping = {
            "make_transfer": "make_transfer",
            "check_balance": "check_balance",
            "other": "other",
            # na wszelki wypadek, gdyby zwrócił po polsku
            "przelew": "make_transfer",
            "saldo": "check_balance",
        }

        return mapping.get(intent_raw, "other")

    except Exception as e:
        # w razie problemów z LLM – nie blokujemy całej aplikacji
        print("[WARN] detect_intent LLM error:", e)
        return "other"


def ask_llm(message: str, context: str) -> str:
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

    content = completion.choices[0].message.content or ""
    return content.strip()
