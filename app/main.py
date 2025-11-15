from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from .db import Base, engine, get_db
from . import banking
from .api import chat, twilio

# Initialize the database
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Collab Voice Assistant")

# CORS – required for Twilio Voice SDK in the browser
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # OK for demo, restrict for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    """Seed demo data when the application starts."""
    with next(get_db()) as db:
        banking.seed_data(db)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def serve_index():
    """
    Returns index.html (the frontend for Twilio Voice SDK).
    Assumes index.html is located in the project root directory.
    """
    index_path = Path("index.html")
    return index_path.read_text(encoding="utf-8")


# Register HTTP and Twilio routers
app.include_router(chat.router)
app.include_router(twilio.router)
