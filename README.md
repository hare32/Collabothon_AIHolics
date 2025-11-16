# VERA - Voice Enabled Reliable Assistant

**(AI)holics** solution for 2025 Commarzbank Collabothon challenge.

Built with:

- **FastAPI**
- **Groq LLM**
- **Twilio Voice SDK & TwiML**
- **SQLite + SQLAlchemy**
- **Docker**

## Features

### 1. Voice authentication

Multi-step flow using Twilio:

1. Verify the caller’s **full name**
2. Verify **last 4 digits of ID**
3. Verify **4-digit PIN**
4. On success, redirect to the main assistant

### 2. Voice banking assistant

After successful authentication, the user talks to the banking assistant. It can:

- **Make transfers** to saved contacts (e.g. _"Send 50 PLN to my mom"_)
- Use **“same amount as last time”** logic based on transaction history
- **Confirm or cancel** transfers with a 2-step confirmation flow
- Answer **balance** questions (e.g. _"What's my balance?"_)
- Show **recent transfers** (e.g. _"Show my last 3 transfers"_)
- Fall back to a general **LLM-based answer** for other questions

## Requirements

- **Python**: 3.10+ recommended
- **Pip / virtualenv**
- **Groq API key**
- **Twilio account** with:

  - Account SID
  - API Key + API Secret
  - A **Twilio TwiML App** (for the Voice SDK)

- (Optional) `ngrok` or similar to expose your local server to Twilio

## Environment variables – `.env` example

Create a `.env` file in the project root (next to `requirements.txt`) with the following content:

```env
# Groq LLM API key (required)
GROQ_API_KEY=your_groq_api_key_here

# Database URL
# Default is SQLite file in the project root:
# sqlite:///./app.db
# You can override this with PostgreSQL or any SQLAlchemy-supported DB.
DATABASE_URL=sqlite:///./app.db

# Twilio credentials (required for voice flows)
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_API_KEY=SKxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_API_SECRET=your_twilio_api_key_secret_here

# TwiML App SID used by the Voice SDK (outgoing_application_sid)
TWIML_APP_SID=APxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# Demo backend user ID (should match the seeded user in seed.py)
BACKEND_USER_ID=user-1
```

> The app loads these environment variables via [`python-dotenv`](https://pypi.org/project/python-dotenv/) in `app/config.py`.

## Installation

1. **Clone the repository**

   ```bash
   git clone https://github.com/your-org/Collabothon_AIHolics.git
   cd Collabothon_AIHolics
   ```

2. **Create and activate a virtual environment**

   ```bash
   python -m venv .venv
   source .venv/bin/activate        # Linux / macOS
   # .venv\Scripts\activate         # Windows (PowerShell / cmd)
   ```

3. **Install dependencies**

   ```bash
   pip install -r requirements.txt
   ```

4. **Create `.env`**

   As shown in the section above.

## Running the backend

Run the FastAPI app with `uvicorn`:

```bash
uvicorn app.main:app --reload
```

By default, it will start on `http://127.0.0.1:8000`.

On startup, the app will:

- Create DB schema (SQLite by default) via `Base.metadata.create_all`
- Seed demo data (user, account, contacts, transaction history)

### Health check

```bash
curl http://127.0.0.1:8000/health
# -> {"status": "ok"}
```

## Twilio Voice setup (phone calls)

The system is designed to be used primarily **via a real phone call**.  
A caller dials a Twilio phone number, goes through voice authentication, and then interacts with the banking assistant.

### 1. Expose your local server (ngrok)

Twilio must be able to access your backend from the public internet.

```bash
ngrok http 8000
```

This will give you a public URL, for example:

```
https://abcd-1234.eu.ngrok.io
```

We will refer to this as **PUBLIC_URL**.

---

### 2. Configure TwiML App & connect a phone number (Twilio Console)

In the Twilio Console:

1. Create a **TwiML App** (or use an existing one).

2. Set the **Voice Request URL** to your authentication endpoint:

3. Save the TwiML App and copy its **SID** — this becomes your `TWIML_APP_SID`.

4. Assign the TwiML App to a **Twilio phone number** under _Voice & Fax → A CALL COMES IN_.
   Now every time someone calls this number, Twilio will invoke your server.

From the user’s perspective, it works like a normal phone call to a bank helpline.

---

## Helpers

### CLI client

[`helpers/cli_client.py`](helpers/cli_client.py) is a very simple text client:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python helpers/cli_client.py
```

You can type messages like:

- `Send 50 PLN to my mom`
- `What is my balance?`
- `Show my last 3 transfers`

Type `exit` to quit.

### Local voice agent (experimental)

[`helpers/voice_agent.py`](helpers/voice_agent.py) uses:

- `speech_recognition` (microphone + Google Speech API)
- `pyttsx3` for local TTS
- The `/assistant/chat` endpoint

> It **won’t work inside WSL** or environments without a microphone. You need to run it on a system with an accessible audio input device (e.g. native Windows/macOS/Linux).
