"""Pytest configuration and fixtures."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Callable, Generator
from contextlib import asynccontextmanager

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import StaticPool

from zrun_base.config import BaseServiceConfig
from zrun_base.logic.domain import CreateSkuInput, SkuDomain
from zrun_base.logic.sku import SkuLogic
from zrun_base.repository.repos import SkuRepository
from zrun_base.repository.schema import create_sku_table
from zrun_base.servicers.sku_servicer import SkuServicer
from zrun_core import USER_ID_CTX_KEY, get_async_session


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop]:
    """Create an event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def test_engine() -> AsyncGenerator[AsyncEngine]:
    """Create a test SQLAlchemy engine.

    This fixture creates an in-memory SQLite database for testing.
    """
    # Create engine with in-memory SQLite
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # Create schema
    await create_sku_table(engine)

    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
async def test_db(test_engine: AsyncEngine) -> AsyncGenerator[AsyncSession]:
    """Create a test database session.

    This fixture creates a new session for each test.
    """
    async with get_async_session(test_engine) as session:
        yield session


@pytest.fixture
def sku_repo(test_db: AsyncSession) -> SkuRepository:
    """Create a SKU repository with test database."""
    return SkuRepository(session=test_db)


@pytest.fixture
def sku_logic(sku_repo: SkuRepository) -> SkuLogic:
    """Create a SKU logic instance with test repository."""
    return SkuLogic(repo=sku_repo)


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


@pytest.fixture
def session_factory(
    test_engine: AsyncEngine,
) -> Callable[[], AsyncGenerator[AsyncSession]]:
    """Create a session factory for servicer tests."""

    @asynccontextmanager
    async def _factory() -> AsyncGenerator[AsyncSession]:
        async with get_async_session(test_engine) as session:
            yield session

    return _factory


@pytest.fixture
def sku_servicer(
    sku_logic: SkuLogic,
    session_factory: Callable[[], AsyncGenerator[AsyncSession]],
) -> SkuServicer:
    """Create a SKU servicer with test logic and session factory."""
    return SkuServicer(logic=sku_logic, session_factory=session_factory)
