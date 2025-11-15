from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..schemas import ChatRequest, ChatResponse
from ..assistant import process_message

router = APIRouter(prefix="/assistant", tags=["assistant"])


@router.post("/chat", response_model=ChatResponse)
def assistant_chat(req: ChatRequest, db: Session = Depends(get_db)):
    reply, intent, _ = process_message(req.message, req.user_id, db)
    return ChatResponse(reply=reply, intent=intent)
