from typing import List, Tuple, Optional

from groq import Groq
from .config import GROQ_API_KEY

if not GROQ_API_KEY:
    raise RuntimeError("Brak GROQ_API_KEY w .env – ustaw go przed uruchomieniem.")

client = Groq(api_key=GROQ_API_KEY)

DEFAULT_MODEL = "llama-3.1-8b-instant"


def detect_intent(message: str, history: Optional[List[Tuple[str, str]]] = None) -> str:
    """
    Wykrywa intencję użytkownika za pomocą LLM, uwzględniając historię rozmowy.
    Zwraca jeden z trzech stringów:
    - "make_transfer"  -> użytkownik chce zrobić przelew
    - "check_balance"  -> użytkownik chce sprawdzić saldo / stan konta
    - "other"          -> wszystko inne
    """

    # z historii bierzemy kilka ostatnich wypowiedzi, żeby model wiedział, o czym była mowa
    history_text = ""
    if history:
        last_turns = history[-6:]  # max ~3 wymiany
        lines = []
        for role, msg in last_turns:
            who = "Klient" if role == "user" else "Asystent"
            lines.append(f"{who}: {msg}")
        history_text = "\n".join(lines)

    system_prompt = (
        "Jesteś klasyfikatorem intencji w asystencie bankowym.\n"
        "Klient mówi po polsku. Na podstawie rozmowy zwróć TYLKO jedno słowo:\n"
        "- make_transfer  jeśli chce wykonać przelew lub zapłacić komuś pieniądze\n"
        "- check_balance  jeśli pyta o saldo, stan konta, ile ma pieniędzy\n"
        "- other          jeśli wypowiedź nie dotyczy przelewu ani salda\n\n"
        "Bierz pod uwagę historię, np. gdy wcześniej klient mówił o przelewie,\n"
        "a teraz podaje tylko kwotę ('50 zł'), to intencja nadal jest make_transfer.\n\n"
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

    if history_text:
        user_prompt = (
            f"Oto fragment dotychczasowej rozmowy:\n{history_text}\n\n"
            f"Ostatnie zdanie klienta: {message}\n"
            "Na tej podstawie zwróć tylko etykietę intencji."
        )
    else:
        user_prompt = message

    try:
        completion = client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
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


def extract_recipient(
    message: str, history: Optional[List[Tuple[str, str]]] = None
) -> Optional[str]:
    """
    Wyciąga z wypowiedzi nazwę/określenie odbiorcy przelewu za pomocą LLM.

    Przykłady:
      - 'Wyślij 150 zł do Jana Kowalskiego' -> 'Jan Kowalski'
      - 'Przelej 200 zł na fundusz alimentacyjny' -> 'fundusz alimentacyjny'
      - 'Daj sąsiadowi 50 zł' -> 'sąsiad'
      - jeśli brak jasnego odbiorcy -> zwraca None

    Zasada: model ma zwrócić TYLKO nazwę / opis odbiorcy
    (bez kwoty, bez dodatkowych słów), albo słowo 'NONE'.
    """

    history_text = ""
    if history:
        last_turns = history[-6:]
        lines = []
        for role, msg in last_turns:
            who = "Klient" if role == "user" else "Asystent"
            lines.append(f"{who}: {msg}")
        history_text = "\n".join(lines)

    system_prompt = (
        "Jesteś ekstraktorem danych w asystencie bankowym.\n"
        "Na podstawie wypowiedzi klienta wyodrębniasz nazwę odbiorcy przelewu.\n"
        "Zwróć TYLKO nazwę odbiorcy (np. 'Jan Kowalski', 'mój sąsiad', 'fundusz alimentacyjny').\n"
        "Usuń z odpowiedzi kwoty, waluty i zbędne słowa.\n"
        "Jeśli w wypowiedzi NIE ma informacji o odbiorcy, zwróć dokładnie słowo: NONE.\n"
        "Nie dodawaj żadnych komentarzy, wyjaśnień ani innych słów."
    )

    if history_text:
        user_prompt = (
            f"Oto fragment dotychczasowej rozmowy:\n{history_text}\n\n"
            f"Ostatnie zdanie klienta: {message}\n"
            "Na tej podstawie zwróć tylko nazwę odbiorcy lub NONE."
        )
    else:
        user_prompt = message

    try:
        completion = client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.0,
            max_tokens=20,
        )

        content = completion.choices[0].message.content or ""
        recipient_raw = content.strip()

        if not recipient_raw:
            return None

        if recipient_raw.upper() == "NONE":
            return None

        return recipient_raw

    except Exception as e:
        print("[WARN] extract_recipient LLM error:", e)
        return None


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
