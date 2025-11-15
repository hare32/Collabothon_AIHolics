from groq import Groq
from .config import GROQ_API_KEY

if not GROQ_API_KEY:
    raise RuntimeError("Missing GROQ_API_KEY in .env – set it before running.")

client = Groq(api_key=GROQ_API_KEY)

DEFAULT_MODEL = "llama-3.1-8b-instant"


def detect_intent(message: str) -> str:
    msg = message.lower()

    # Check balance intent
    if (
        "balance" in msg
        or "account balance" in msg
        or "how much money" in msg
        or "how much do i have" in msg
    ):
        return "check_balance"

    # Make transfer intent
    if (
        "transfer" in msg
        or "send money" in msg
        or "wire" in msg
        or "make a payment" in msg
        or "pay someone" in msg
    ):
        return "make_transfer"

    return "other"


def ask_llm(message: str, context: str) -> str:
    prompt = (
        "You are a virtual banking assistant. "
        "Answer briefly and clearly in English.\n\n"
        f"Customer context:\n{context}\n\n"
        f"Customer question: {message}\n"
    )

    completion = client.chat.completions.create(
        model=DEFAULT_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a helpful banking assistant speaking English. "
                    "Always respond briefly and clearly in English. "
                    "Do not perform identity verification yourself – "
                    "assume the customer has already been authenticated."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
    )

    content = completion.choices[0].message.content or ""
    return content.strip()
