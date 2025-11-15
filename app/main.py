# app/main.py
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from .db import Base, engine, get_db
from .seed import seed_demo_data
from .api import chat
from .api import twilio
from .api import banking as banking_api
from .api import auth_voice

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Collab Voice Assistant")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup() -> None:
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


app.include_router(auth_voice.router)
app.include_router(twilio.router)
app.include_router(chat.router)
app.include_router(banking_api.router)
