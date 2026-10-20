"""GET /api/history/<session_id>/ — conversation, diagnoses, uploads."""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import ChatMessage, Diagnosis, MediaUpload
from app.routes.common import error_response
from app.schemas import chat_message_out, diagnosis_out, media_upload_out
from app.services.session_store import get_session

router = APIRouter()


@router.get("/history/{session_id}/")
async def conversation_history(
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    session = await get_session(db, session_id)
    if session is None:
        return error_response(404, "Unknown session id.")

    messages = (
        await db.scalars(
            select(ChatMessage)
            .where(ChatMessage.session_id == session.id)
            .order_by(ChatMessage.created_at)
        )
    ).all()
    diagnoses = (
        await db.scalars(
            select(Diagnosis)
            .where(Diagnosis.session_id == session.id)
            .order_by(Diagnosis.created_at.desc())
        )
    ).all()
    uploads = (
        await db.scalars(
            select(MediaUpload)
            .where(MediaUpload.session_id == session.id)
            .order_by(MediaUpload.created_at)
        )
    ).all()

    return {
        "session_id": str(session.id),
        "vehicle": {
            "make": session.vehicle_make,
            "model": session.vehicle_model,
            "year": session.vehicle_year,
            "fuel": session.vehicle_fuel,
        },
        "messages": [chat_message_out(message) for message in messages],
        "diagnoses": [diagnosis_out(diagnosis) for diagnosis in diagnoses],
        "uploads": [media_upload_out(upload) for upload in uploads],
    }
