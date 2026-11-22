"""GET /api/context/{session_id}/ — diagnostic context for the mechanic console."""
from fastapi import APIRouter

from app.routes.common import error_response
from app.services import mongo_store

router = APIRouter()


@router.get("/context/{session_id}/")
async def context(session_id: str):
    data = await mongo_store.get_context(session_id)
    if data is None:
        return error_response(503, "Diagnostic context store is unavailable.")
    return data
