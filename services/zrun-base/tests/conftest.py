"""Pytest configuration and fixtures."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Generator
from typing import TYPE_CHECKING

import pytest

from zrun_base.config import BaseServiceConfig
from zrun_base.logic.sku import CreateSkuInput, SkuDomain, SkuLogic
from zrun_base.repository.sqlite import (
    SqliteSkuRepository,
    get_in_memory_connection,
)
from zrun_base.repository.sqlite import (
    create_sku_table as create_sqlite_table,
)
from zrun_base.servicers.sku_servicer import SkuServicer
from zrun_core import USER_ID_CTX_KEY

if TYPE_CHECKING:
    import sqlite3


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop]:
    """Create an event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def test_db() -> AsyncGenerator[sqlite3.Connection]:
    """Create a test SQLite database.

    This fixture creates an in-memory SQLite database and sets up the test schema.
    """

    conn = get_in_memory_connection()
    await create_sqlite_table(conn)
    try:
        yield conn
    finally:
        # SQLite doesn't need closing for in-memory databases
        pass


@pytest.fixture
def sku_repo(test_db: sqlite3.Connection) -> SqliteSkuRepository:
    """Create a SKU repository with test database."""
    return SqliteSkuRepository(connection=test_db)


@pytest.fixture
def sku_logic(sku_repo: SqliteSkuRepository) -> SkuLogic:
    """Create a SKU logic instance with test repository."""
    return SkuLogic(repo=sku_repo)


@pytest.fixture
def sku_servicer(sku_logic: SkuLogic) -> SkuServicer:
    """Create a SKU servicer with test logic."""
    return SkuServicer(logic=sku_logic)


@pytest.fixture
def test_user_id() -> str:
    """Get a test user ID."""
    return "test-user-123"


@pytest.fixture(autouse=True)
async def set_test_user_context(test_user_id: str) -> AsyncGenerator[None]:
    """Set the test user context for all tests."""
    token = USER_ID_CTX_KEY.set(test_user_id)
    yield
    USER_ID_CTX_KEY.reset(token)


@pytest.fixture
async def test_sku(sku_logic: SkuLogic) -> SkuDomain:
    """Create a test SKU in the database."""
    input = CreateSkuInput(
        code="TEST-SKU-001",
        name="Test SKU",
    )
    return await sku_logic.create_sku(input)


@pytest.fixture
def test_config() -> BaseServiceConfig:
    """Get test configuration."""
    return BaseServiceConfig()
