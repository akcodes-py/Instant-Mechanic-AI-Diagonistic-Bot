"""POST /rank/eta — ETA ranking for the Kotlin dispatch service."""
from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services import ranker

router = APIRouter()


class CandidateIn(BaseModel):
    mechanic_id: str
    h3_res8: str = ""
    lat: float = 0.0
    lon: float = 0.0


class RankRequest(BaseModel):
    booking_id: str
    origin_h3: str
    candidates: list[CandidateIn] = Field(default_factory=list, max_length=200)


@router.post("/rank/eta")
async def rank_eta(payload: RankRequest) -> dict:
    return ranker.rank(
        payload.booking_id,
        payload.origin_h3,
        [item.model_dump() for item in payload.candidates],
    )
