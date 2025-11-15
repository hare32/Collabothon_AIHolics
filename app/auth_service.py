from fastapi import FastAPI, HTTPException, Header, Depends
from pydantic import BaseModel
import secrets
import httpx
import os
from typing import Optional, Dict, Any
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Bank Auth Gateway")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app = FastAPI(title="Bank Auth Gateway")

BOT_BASE_URL = os.environ.get("BOT_BASE_URL", "http://localhost:8000")
BOT_CHAT_PATH = os.environ.get("BOT_CHAT_PATH", "/assistant/chat")

USERS: Dict[str, Dict[str, str]] = {
    "user-1": {
        "pesel_last4": "1234",
        "telepin": "4321",
        "mother_maiden_name": "NOWAK",
    }
}

SESSIONS: Dict[str, str] = {}

class AuthRequest(BaseModel):
    user_id: str
    pesel_last4: str
    telepin: str
    mother_maiden_name: str


class AuthResponse(BaseModel):
    success: bool
    message: str
    token: Optional[str] = None


class ChatProxyRequest(BaseModel):
    payload: Dict[str, Any]

def verify_user(req: AuthRequest) -> bool:
    user = USERS.get(req.user_id)
    if not user:
        return False

    return (
        user["pesel_last4"] == req.pesel_last4
        and user["telepin"] == req.telepin
        and user["mother_maiden_name"].lower()
        == req.mother_maiden_name.lower().strip()
    )


def get_user_id_from_token(
    authorization: str = Header(..., alias="Authorization")
) -> str:
    """
    Oczekuje nagłówka:
        Authorization: Bearer <token>
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Brak Bearer tokenu.")

    token = authorization.removeprefix("Bearer ").strip()
    user_id = SESSIONS.get(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Nieprawidłowy lub wygasły token.")

    return user_id

@app.post("/auth/verify", response_model=AuthResponse)
async def authenticate(req: AuthRequest):
    if not verify_user(req):
        raise HTTPException(status_code=401, detail="Błędne dane uwierzytelniające.")

    token = secrets.token_urlsafe(32)
    SESSIONS[token] = req.user_id

    message = (
        "Dzień dobry! Uwierzytelnienie przebiegło pomyślnie. "
        "Za chwilę połączę Cię z asystentem."
    )

    return AuthResponse(success=True, message=message, token=token)


@app.post("/proxy/chat")
async def proxy_chat(
    req: ChatProxyRequest,
    user_id: str = Depends(get_user_id_from_token),
):

    payload = dict(req.payload)
    payload.setdefault("user_id", user_id)

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            BOT_BASE_URL + BOT_CHAT_PATH,
            json=payload,
        )

    if resp.status_code >= 400:
        raise HTTPException(
            status_code=resp.status_code,
            detail=f"Błąd bota: {resp.text}",
        )

    return resp.json()
