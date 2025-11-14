from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from .db import Base, engine, get_db
from . import banking
from .api import chat, twilio

# inicjalizacja bazy
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Collab Voice Assistant")

# CORS – Twilio Voice SDK w przeglądarce
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # na demo może zostać *, do produkcji zawęź
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    # seed danych demo
    with next(get_db()) as db:
        banking.seed_data(db)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def serve_index():
    """
    Zwraca index.html (frontend Twilio Voice SDK).
    Zakładam, że index.html leży w katalogu głównym projektu.
    """
    index_path = Path("index.html")
    return index_path.read_text(encoding="utf-8")


# rejestracja routerów HTTP i Twilio
app.include_router(chat.router)
app.include_router(twilio.router)
