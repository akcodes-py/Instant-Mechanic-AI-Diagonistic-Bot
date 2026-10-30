"""Booking create/detail endpoints. No AI dependency."""
from typing import Any

from fastapi import APIRouter, Body, Depends
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Booking, ChatSession, Diagnosis
from app.routes.common import error_response
from app.schemas import (
    BookingRequest,
    booking_out,
    diagnosis_out,
    validation_errors,
)
from app.services.session_store import get_session, parse_uuid

router = APIRouter()


@router.post("/booking/")
async def create_booking(
    body: dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_db),
):
    if body.get("website"):
        return error_response(400, "Request rejected.")

    try:
        request = BookingRequest.model_validate(body)
    except ValidationError as exc:
        return JSONResponse(status_code=400, content=validation_errors(exc))

    session = await get_session(db, request.session_id)
    if request.session_id and session is None:
        return JSONResponse(
            status_code=400, content={"session_id": "Unknown session id."}
        )

    diagnosis_row = None
    if request.diagnosis_id:
        diagnosis_uuid = parse_uuid(request.diagnosis_id)
        diagnosis_row = (
            await db.get(Diagnosis, str(diagnosis_uuid)) if diagnosis_uuid else None
        )
        if diagnosis_row is None:
            return JSONResponse(
                status_code=400, content={"diagnosis_id": "Unknown diagnosis id."}
            )
        if session and diagnosis_row.session_id != session.id:
            return JSONResponse(
                status_code=400,
                content={"diagnosis": "Diagnosis does not belong to this chat session."},
            )
        if not session:
            session = await db.get(ChatSession, diagnosis_row.session_id)

    booking = Booking(
        session_id=session.id if session else None,
        diagnosis_id=diagnosis_row.id if diagnosis_row else None,
        name=request.name,
        phone=request.phone,
        service_type=request.service_type,
        vehicle_details=(request.vehicle_details or "")[:255],
        location=request.location,
        scheduled_at=(request.scheduled_at or "")[:80],
        notes=request.notes or "",
        status="pending",
    )
    db.add(booking)
    await db.commit()
    await db.refresh(booking)

    output = booking_out(booking)
    output["message"] = (
        "Booking received. Our team will call to confirm. For urgent help call "
        "+91 6392077642."
    )
    return JSONResponse(status_code=201, content=output)


@router.get("/booking/{id}/")
async def booking_detail(
    id: str,
    session_id: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    booking_uuid = parse_uuid(id)
    if booking_uuid is None:
        return error_response(404, "Invalid booking id.")

    booking = await db.get(Booking, str(booking_uuid))
    if booking is None:
        return error_response(404, "Booking not found.")

    # Session isolation: if a session_id query is given, it must match.
    if session_id:
        session = await get_session(db, session_id)
        if session is None or (booking.session_id and booking.session_id != session.id):
            return error_response(404, "Booking not found for this session.")

    output = booking_out(booking)
    if booking.diagnosis_id:
        diagnosis_row = await db.get(Diagnosis, booking.diagnosis_id)
        if diagnosis_row is not None:
            output["diagnosis"] = diagnosis_out(diagnosis_row)
    return output
