# app/main.py
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from .db import Base, engine, get_db
from .seed import seed_demo_data
from .api import chat, twilio, banking as banking_api
from .api import auth_voice  # NEW

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Collab Voice Assistant")

# CORS – Twilio Voice SDK in the browser
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    # Seed demo data
    with next(get_db()) as db:
        seed_demo_data(db)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def serve_index():
    """
    Returns index.html (Twilio Voice SDK frontend).
    Assumes index.html is in the project root directory.
    """
    index_path = Path("index.html")
    return index_path.read_text(encoding="utf-8")


# NEW: auth router – nie zmienia istniejących ścieżek
app.include_router(auth_voice.router)

# STARE – bez zmian
app.include_router(chat.router)
app.include_router(twilio.router)
app.include_router(banking_api.router)
