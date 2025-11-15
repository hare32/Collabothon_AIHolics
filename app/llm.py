from typing import List, Tuple, Optional, Dict

from groq import Groq
from .config import GROQ_API_KEY

if not GROQ_API_KEY:
    raise RuntimeError("Missing GROQ_API_KEY in .env – set it before running.")

client = Groq(api_key=GROQ_API_KEY)

DEFAULT_MODEL = "llama-3.1-8b-instant"


def detect_intent(message: str, history: Optional[List[Tuple[str, str]]] = None) -> str:
    """
    Detects the user's intent using LLM, taking conversation history into account.
    Returns one of four strings:
    - "make_transfer"   -> user wants to make a transfer / send money
    - "check_balance"   -> user wants to check account balance
    - "show_history"    -> user wants to see transfer history / recent transactions
    - "other"           -> anything else
    """

    # Use a few last turns so the model knows the context
    history_text = ""
    if history:
        last_turns = history[-6:]  # up to ~3 exchanges
        lines = []
        for role, msg in last_turns:
            who = "Customer" if role == "user" else "Assistant"
            lines.append(f"{who}: {msg}")
        history_text = "\n".join(lines)

    system_prompt = (
        "You are an intent classifier in a banking voice assistant.\n"
        "The customer speaks English. Based on the conversation, return ONLY one word:\n"
        "- make_transfer  if the customer wants to make a transfer or send money\n"
        "- check_balance  if the customer asks about balance, account status, how much money they have\n"
        "- show_history   if the customer asks about transfer history, recent transactions\n"
        "- other          if the utterance does not match the above\n\n"
        "Take conversation history into account, e.g. if the customer previously talked about a transfer,\n"
        "and now only says an amount ('50'), the intent is still make_transfer.\n\n"
        "Examples:\n"
        "U: Send 50 to my neighbor\n"
        "A: make_transfer\n"
        "U: Make a transfer of 50 to my neighbor\n"
        "A: make_transfer\n"
        "U: How much money do I have?\n"
        "A: check_balance\n"
        "U: What's my balance?\n"
        "A: check_balance\n"
        "U: What were my last transfers?\n"
        "A: show_history\n"
        "U: Show my transaction history\n"
        "A: show_history\n"
        "U: Tell me a joke\n"
        "A: other\n"
        "Do not add any explanations, comments or extra text."
    )

    if history_text:
        user_prompt = (
            f"Here is part of the conversation so far:\n{history_text}\n\n"
            f"Customer's last sentence: {message}\n"
            "Based on this, return only the intent label."
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

        # Simple normalization, in case model changes capitalization or words
        mapping = {
            "make_transfer": "make_transfer",
            "check_balance": "check_balance",
            "show_history": "show_history",
            "other": "other",
            # in case it returns English synonyms
            "transfer": "make_transfer",
            "balance": "check_balance",
            "history": "show_history",
            "transactions": "show_history",
        }

        return mapping.get(intent_raw, "other")

    except Exception as e:
        # On LLM problems – do not block the whole app
        print("[WARN] detect_intent LLM error:", e)
        return "other"


def extract_recipient(
    message: str, history: Optional[List[Tuple[str, str]]] = None
) -> Optional[str]:
    """
    Extracts the recipient name/description from the utterance using LLM.

    Examples:
      - 'Send 150 PLN to John Smith' -> 'John Smith'
      - 'Transfer 200 PLN to child support fund' -> 'child support fund'
      - 'Give 50 PLN to my neighbor' -> 'my neighbor'
      - if no clear recipient -> returns None

    Rule: the model must return ONLY the recipient name/description
    (no amount, no currency, no extra words), or the word 'NONE'.
    """

    history_text = ""
    if history:
        last_turns = history[-6:]
        lines = []
        for role, msg in last_turns:
            who = "Customer" if role == "user" else "Assistant"
            lines.append(f"{who}: {msg}")
        history_text = "\n".join(lines)

    system_prompt = (
        "You are a data extractor in a banking assistant.\n"
        "Based on the customer's utterance, extract the transfer recipient name.\n"
        "Return ONLY the recipient name/description (e.g. 'John Smith', 'my neighbor', 'child support fund').\n"
        "Remove amounts, currencies and unnecessary words.\n"
        "If the utterance does NOT contain recipient information, return exactly: NONE.\n"
        "Do not add any comments, explanations or other words."
    )

    if history_text:
        user_prompt = (
            f"Here is part of the conversation so far:\n{history_text}\n\n"
            f"Customer's last sentence: {message}\n"
            "Based on this, return only the recipient name or NONE."
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
        "You are a virtual banking assistant. "
        "You respond briefly and clearly in English.\n\n"
        f"Customer context:\n{context}\n\n"
        f"Customer question: {message}\n"
    )

    completion = client.chat.completions.create(
        model=DEFAULT_MODEL,
        messages=[
            {
                "role": "system",
                "content": "You are a helpful banking assistant speaking English.",
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
    )

    content = completion.choices[0].message.content or ""
    return content.strip()


def match_contact_label(label: str, contacts: List[Dict[str, str]]) -> Optional[str]:
    """
    Uses LLM to map a phrase from speech (e.g. 'to my mom', 'for my grandson')
    to one of the contacts.

    contacts: list of dictionaries:
      {
        "nickname": "mom",
        "full_name": "Barbara Smith"
      }

    Returns:
      - the nickname of the contact (e.g. 'mom') if LLM finds a sensible match
      - None if no clear match (LLM should return 'NONE')
    """
    label = (label or "").strip()
    if not label or not contacts:
        return None

    # Build contact list text for LLM
    lines = []
    for c in contacts:
        nick = c.get("nickname", "")
        full = c.get("full_name", "")
        lines.append(f"- nickname: {nick}, name: {full}")
    contacts_text = "\n".join(lines)

    system_prompt = (
        "You are a module that matches the transfer recipient to saved contacts.\n"
        "The customer speaks English and uses phrases such as 'to my mom', 'for my grandson', "
        "'to the child support fund', etc.\n\n"
        "You get:\n"
        "- a PHRASE from the customer describing the recipient\n"
        "- a LIST of contacts, each having 'nickname' and full name\n\n"
        "Your task:\n"
        "- choose the contact that best matches the customer's phrase\n"
        "- return EXACTLY the 'nickname' value of the chosen contact\n"
        "- if no contact fits reasonably, return exactly: NONE\n\n"
        "Do not add any explanations, comments or extra text."
    )

    user_prompt = (
        f"CUSTOMER PHRASE: {label}\n\n"
        f"CONTACT LIST:\n{contacts_text}\n\n"
        "Return only the nickname of the best matching contact or NONE."
    )

    try:
        completion = client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.0,
            max_tokens=10,
        )

        content = completion.choices[0].message.content or ""
        raw = content.strip()

        if not raw:
            return None

        if raw.upper() == "NONE":
            return None

        return raw

    except Exception as e:
        print("[WARN] match_contact_label LLM error:", e)
        return None
