"""Best-effort MongoDB metadata store for the assigned mechanic's context.

Disabled by default (ENABLE_MONGO=False). Every call is time-bounded and returns
False/None on failure, so chat -> diagnosis -> booking never depends on MongoDB.
No raw media binaries are stored here; only object keys and real detections.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from app.config import settings

logger = logging.getLogger(__name__)

_CLIENT = None


def _collection(name: str):
    if not settings.ENABLE_MONGO or not settings.MONGODB_URL:
        return None
    global _CLIENT
    try:
        if _CLIENT is None:
            from motor.motor_asyncio import AsyncIOMotorClient

            _CLIENT = AsyncIOMotorClient(
                settings.MONGODB_URL, serverSelectionTimeoutMS=settings.MONGO_TIMEOUT_MS
            )
        return _CLIENT[settings.MONGODB_DB][name]
    except Exception:
        return None


async def _insert(name: str, document: dict) -> bool:
    collection = _collection(name)
    if collection is None:
        return False
    try:
        await asyncio.wait_for(collection.insert_one(document), timeout=settings.MONGO_TIMEOUT_MS / 1000)
        return True
    except Exception:
        logger.warning("Mongo write failed: %s", type(Exception).__name__)
        return False


async def store_message(session_id: str, role: str, content: str, ai_used: bool = False) -> bool:
    return await _insert(
        "chat_messages",
        {
            "session_id": session_id,
            "role": role,
            "content": content[:4000],
            "ai_used": bool(ai_used),
            "created_at": datetime.now(timezone.utc),
        },
    )


async def store_upload(
    session_id: str,
    object_key: str,
    kind: str,
    size_bytes: int,
    analyzed: bool,
    detections: list[dict] | None = None,
    reliable_labels: list[str] | None = None,
) -> bool:
    return await _insert(
        "uploaded_media",
        {
            "session_id": session_id,
            "object_key": object_key,
            "kind": kind,
            "size_bytes": size_bytes,
            "analyzed": bool(analyzed),
            "detections": (detections or [])[:8],
            "reliable_labels": (reliable_labels or [])[:8],
            "created_at": datetime.now(timezone.utc),
        },
    )


async def get_context(session_id: str) -> dict | None:
    """Return stored chat/photo context, or None when the store is unavailable."""
    messages = _collection("chat_messages")
    uploads = _collection("uploaded_media")
    if messages is None or uploads is None:
        return None
    try:
        timeout = settings.MONGO_TIMEOUT_MS / 1000
        history = await asyncio.wait_for(
            messages.find({"session_id": session_id}, {"_id": 0}).sort("created_at", 1).to_list(100),
            timeout,
        )
        media = await asyncio.wait_for(
            uploads.find({"session_id": session_id}, {"_id": 0}).sort("created_at", 1).to_list(50),
            timeout,
        )
        return {"session_id": session_id, "messages": history, "uploads": media}
    except Exception:
        logger.warning("Mongo read failed: %s", type(Exception).__name__)
        return None
