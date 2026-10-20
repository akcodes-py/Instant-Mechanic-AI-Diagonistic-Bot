"""FastAPI application entry point."""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db
from app.routes import booking, chat, diagnosis, health, history, upload


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Path(settings.MEDIA_ROOT).mkdir(parents=True, exist_ok=True)
    await init_db()
    yield


app = FastAPI(
    title="Instant Mechanic API",
    version="2.0.0",
    lifespan=lifespan,
)

if settings.CORS_ALLOW_ALL:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(health.router, prefix="/api")
app.include_router(chat.router, prefix="/api")
app.include_router(upload.router, prefix="/api")
app.include_router(diagnosis.router, prefix="/api")
app.include_router(booking.router, prefix="/api")
app.include_router(history.router, prefix="/api")
