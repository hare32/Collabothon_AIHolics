from typing import List, Tuple, Optional

from groq import Groq
from .config import GROQ_API_KEY

if not GROQ_API_KEY:
    raise RuntimeError("Missing GROQ_API_KEY in .env – set it before running the application.")

client = Groq(api_key=GROQ_API_KEY)

DEFAULT_MODEL = "llama-3.1-8b-instant"


def detect_intent(message: str, history: Optional[List[Tuple[str, str]]] = None) -> str:
    """
    Detects the user's intent using the LLM, taking conversation history into account.
    Returns one of:
    - "make_transfer"  -> user wants to make a money transfer
    - "check_balance"  -> user wants to check their account balance
    - "other"          -> anything else
    """

    # Prepare recent conversation context for the model
    history_text = ""
    if history:
        last_turns = history[-6:]  # last ~3 exchanges
        lines = []
        for role, msg in last_turns:
            who = "User" if role == "user" else "Assistant"
            lines.append(f"{who}: {msg}")
        history_text = "\n".join(lines)

    # --- INTENT CLASSIFICATION PROMPT (ENGLISH VERSION) ---
    system_prompt = (
        "You are an intent classifier for a banking voice assistant.\n"
        "Based on the conversation, return ONLY ONE word:\n"
        "- make_transfer  → if the user wants to send money or make a transfer\n"
        "- check_balance  → if the user asks about their balance or account status\n"
        "- other          → if the message is not about transfers or balance\n\n"
        "Take the conversation history into account — for example, "
        "if the user previously said they want to make a transfer, "
        "and now only provides an amount ('50 dollars'), the intent is still make_transfer.\n\n"
        "Examples:\n"
        "U: Send my neighbor 50 dollars.\n"
        "A: make_transfer\n"
        "U: Transfer 50 dollars to my neighbor.\n"
        "A: make_transfer\n"
        "U: How much money do I have?\n"
        "A: check_balance\n"
        "U: What's my balance?\n"
        "A: check_balance\n"
        "U: Tell me a joke.\n"
        "A: other\n\n"
        "Do NOT add explanations, comments, or any extra text."
    )

    if history_text:
        user_prompt = (
            f"Here is the recent conversation:\n{history_text}\n\n"
            f"User's latest message: {message}\n"
            "Return ONLY the intent label."
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

        # Normalize unexpected outputs
        mapping = {
            "make_transfer": "make_transfer",
            "check_balance": "check_balance",
            "other": "other",
        }

        return mapping.get(intent_raw, "other")

    except Exception as e:
        print("[WARN] detect_intent LLM error:", e)
        return "other"


def ask_llm(message: str, context: str) -> str:
    """
    Sends the user's question + context to the LLM
    and returns the assistant's natural language answer.
    """

    # --- MAIN ASSISTANT PROMPT (ENGLISH VERSION) ---
    prompt = (
        "You are a virtual banking assistant. "
        "Respond clearly, briefly, and in English.\n\n"
        f"User context:\n{context}\n\n"
        f"User question: {message}\n"
    )

    completion = client.chat.completions.create(
        model=DEFAULT_MODEL,
        messages=[
            {
                "role": "system",
                "content": "You are a helpful English-speaking banking assistant.",
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
    )

    content = completion.choices[0].message.content or ""
    return content.strip()
