from fastapi import APIRouter

from app.models import CommunicationMessage, CommunicationMessageCreate, Notification
from app.services.demo_store import store

router = APIRouter(prefix="/communications", tags=["communications"])


@router.get("/notifications", response_model=list[Notification])
def list_notifications(recipient_id: str | None = None) -> list[Notification]:
    return store.list_notifications(recipient_id)


@router.get("/messages", response_model=list[CommunicationMessage])
def list_messages(donation_id: str | None = None) -> list[CommunicationMessage]:
    return store.list_messages(donation_id)


@router.post("/messages", response_model=CommunicationMessage)
def create_message(payload: CommunicationMessageCreate) -> CommunicationMessage:
    return store.create_message(payload)
