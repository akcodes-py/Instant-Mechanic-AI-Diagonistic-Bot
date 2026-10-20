"""Async test fixtures. The database and media root are isolated per test session."""
import os
import shutil
import tempfile
from pathlib import Path

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

TEST_ROOT = Path(tempfile.mkdtemp(prefix="instant-mechanic-tests-"))
TEST_DB = TEST_ROOT / "test.db"

# These must be set before the application/settings modules are imported.
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB.as_posix()}"
os.environ["MEDIA_ROOT"] = str(TEST_ROOT / "media")
os.environ["GROQ_API_KEY"] = ""
os.environ["CHAT_RATELIMIT_PER_MIN"] = "1000"

from app import models  # noqa: E402,F401  (register tables)
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.services import session_store  # noqa: E402


@pytest_asyncio.fixture(autouse=True)
async def reset_database():
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    session_store._RATE.clear()
    yield


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client


@pytest_asyncio.fixture
async def db_session():
    async with SessionLocal() as session:
        yield session


def pytest_sessionfinish(session, exitstatus):
    # Best effort: Windows may still hold the SQLite file open.
    shutil.rmtree(TEST_ROOT, ignore_errors=True)
