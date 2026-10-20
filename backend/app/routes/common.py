"""Shared response helpers."""
from fastapi.responses import JSONResponse


def error_response(status_code: int, message: str) -> JSONResponse:
    """Return the API's existing {"error": ...} shape instead of FastAPI's detail."""
    return JSONResponse(status_code=status_code, content={"error": message})
