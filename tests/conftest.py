"""Pytest fixtures. Set a dummy token so config can load."""

import os

# Must be set before any import of config
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "0000000000:TEST_TOKEN_FOR_UNIT_TESTS_ONLY")
os.environ.setdefault("DATA_DIR", "./test_data")
os.environ.setdefault("LOG_LEVEL", "WARNING")

import pytest
import pytest_asyncio

from database.database import Database


@pytest_asyncio.fixture
async def db(tmp_path):
    path = tmp_path / "test.db"
    database = Database(path=path)
    await database.connect()
    yield database
    await database.close()
