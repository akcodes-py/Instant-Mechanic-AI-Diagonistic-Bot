"""Small database/session helpers shared by the route modules."""
import time
import uuid
from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import ChatMessage, ChatSession

# Simple in-memory rate limiting (per process; sufficient for this prototype).
_RATE: dict[str, list[float]] = defaultdict(list)


def parse_uuid(value) -> uuid.UUID | None:
    if not value:
        return None
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return None


async def get_session(db: AsyncSession, session_id) -> ChatSession | None:
    uid = parse_uuid(session_id)
    if uid is None:
        return None
    return await db.get(ChatSession, str(uid))


def rate_limited(key: str) -> bool:
    now = time.time()
    window = [stamp for stamp in _RATE[key] if now - stamp < 60]
    limit = settings.CHAT_RATELIMIT_PER_MIN
    if len(window) >= limit:
        _RATE[key] = window
        return True
    window.append(now)
    _RATE[key] = window
    return False


async def history_text(db: AsyncSession, session: ChatSession, limit: int = 12) -> str:
    rows = (
        await db.scalars(
            select(ChatMessage)
            .where(ChatMessage.session_id == session.id)
            .order_by(ChatMessage.created_at.desc())
            .limit(limit)
        )
    ).all()
    return "\n".join(
        f"{message.role}: {message.content[:600]}" for message in reversed(rows)
    )


async def message_count(db: AsyncSession, session: ChatSession) -> int:
    count = await db.scalar(
        select(func.count(ChatMessage.id)).where(ChatMessage.session_id == session.id)
    )
    return int(count or 0)


async def user_message_count(db: AsyncSession, session: ChatSession) -> int:
    count = await db.scalar(
        select(func.count(ChatMessage.id)).where(
            ChatMessage.session_id == session.id,
            ChatMessage.role == "user",
        )
    )
    return int(count or 0)


async def user_messages(db: AsyncSession, session: ChatSession) -> list[ChatMessage]:
    return list(
        (
            await db.scalars(
                select(ChatMessage)
                .where(
                    ChatMessage.session_id == session.id,
                    ChatMessage.role == "user",
                )
                .order_by(ChatMessage.created_at)
            )
        ).all()
    )
