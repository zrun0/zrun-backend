"""Unit tests for SKU logic."""

from __future__ import annotations

import pytest

from zrun_base.logic.sku import CreateSkuInput, SkuDomain, SkuLogic, UpdateSkuInput
from zrun_core.errors import ConflictError, NotFoundError, ValidationError


class MockSkuRepository:
    """Mock SKU repository for testing."""

    def __init__(self) -> None:
        self._skus: dict[str, SkuDomain] = {}
        self._code_index: dict[str, SkuDomain] = {}

    async def create(self, sku: SkuDomain) -> SkuDomain:
        """Create a SKU."""
        self._skus[sku.id] = sku
        self._code_index[sku.code] = sku
        return sku

    async def get_by_id(self, sku_id: str) -> SkuDomain | None:
        """Get a SKU by ID."""
        return self._skus.get(sku_id)

    async def get_by_code(self, code: str) -> SkuDomain | None:
        """Get a SKU by code."""
        return self._code_index.get(code)

    async def update(self, sku: SkuDomain) -> SkuDomain:
        """Update a SKU."""
        if sku.id not in self._skus:
            msg = f"SKU with ID '{sku.id}' not found"
            raise NotFoundError(msg)

        # Update code index if code changed
        old_sku = self._skus[sku.id]
        if old_sku.code != sku.code:
            del self._code_index[old_sku.code]
            self._code_index[sku.code] = sku

        self._skus[sku.id] = sku
        return sku

    async def delete(self, sku_id: str) -> None:
        """Delete a SKU."""
        sku = self._skus.pop(sku_id, None)
        if sku:
            self._code_index.pop(sku.code, None)

    async def list(
        self,
        limit: int = 100,
        offset: int = 0,
    ) -> list[SkuDomain]:
        """List SKUs."""
        return list(self._skus.values())[offset : offset + limit]


@pytest.fixture
def mock_repo() -> MockSkuRepository:
    """Create a mock SKU repository."""
    return MockSkuRepository()


@pytest.fixture
def sku_logic(mock_repo: MockSkuRepository) -> SkuLogic:
    """Create a SKU logic instance with mock repository."""
    return SkuLogic(repo=mock_repo)


class TestSkuLogic:
    """Test cases for SkuLogic."""

    async def test_create_sku_success(self, sku_logic: SkuLogic) -> None:
        """Test successful SKU creation."""
        input = CreateSkuInput(
            code="TEST-SKU-001",
            name="Test SKU",
        )

        sku = await sku_logic.create_sku(input)

        assert sku.id is not None
        assert sku.code == "TEST-SKU-001"
        assert sku.name == "Test SKU"
        assert sku.created_at is not None

    async def test_create_sku_normalizes_code(self, sku_logic: SkuLogic) -> None:
        """Test that SKU code is normalized to uppercase."""
        input = CreateSkuInput(
            code="test-sku-001",
            name="Test SKU",
        )

        sku = await sku_logic.create_sku(input)

        assert sku.code == "TEST-SKU-001"

    async def test_create_sku_trims_whitespace(self, sku_logic: SkuLogic) -> None:
        """Test that whitespace is trimmed from code and name."""
        input = CreateSkuInput(
            code="  TEST-SKU-001  ",
            name="  Test SKU  ",
        )

        sku = await sku_logic.create_sku(input)

        assert sku.code == "TEST-SKU-001"
        assert sku.name == "Test SKU"

    async def test_create_sku_empty_code_raises_error(self, sku_logic: SkuLogic) -> None:
        """Test that empty code raises ValidationError."""
        input = CreateSkuInput(
            code="",
            name="Test SKU",
        )

        with pytest.raises(ValidationError, match="Code is required"):
            await sku_logic.create_sku(input)

    async def test_create_sku_empty_name_raises_error(self, sku_logic: SkuLogic) -> None:
        """Test that empty name raises ValidationError."""
        input = CreateSkuInput(
            code="TEST-SKU-001",
            name="",
        )

        with pytest.raises(ValidationError, match="Name is required"):
            await sku_logic.create_sku(input)

    async def test_create_sku_duplicate_code_raises_error(self, sku_logic: SkuLogic) -> None:
        """Test that duplicate code raises ConflictError."""
        input = CreateSkuInput(
            code="TEST-SKU-001",
            name="Test SKU",
        )

        # Create first SKU
        await sku_logic.create_sku(input)

        # Try to create duplicate
        with pytest.raises(ConflictError, match="already exists"):
            await sku_logic.create_sku(input)

    async def test_get_sku_success(self, sku_logic: SkuLogic) -> None:
        """Test successful SKU retrieval."""
        # Create a SKU first
        input = CreateSkuInput(
            code="TEST-SKU-001",
            name="Test SKU",
        )
        created = await sku_logic.create_sku(input)

        # Get the SKU
        retrieved = await sku_logic.get_sku(created.id)

        assert retrieved.id == created.id
        assert retrieved.code == created.code
        assert retrieved.name == created.name

    async def test_get_sku_not_found_raises_error(self, sku_logic: SkuLogic) -> None:
        """Test that getting non-existent SKU raises NotFoundError."""
        with pytest.raises(NotFoundError, match="not found"):
            await sku_logic.get_sku("non-existent-id")

    async def test_get_sku_empty_id_raises_error(self, sku_logic: SkuLogic) -> None:
        """Test that empty SKU ID raises ValidationError."""
        with pytest.raises(ValidationError, match="SKU ID is required"):
            await sku_logic.get_sku("")

    async def test_update_sku_success(self, sku_logic: SkuLogic) -> None:
        """Test successful SKU update."""
        # Create a SKU first
        input = CreateSkuInput(
            code="TEST-SKU-001",
            name="Test SKU",
        )
        created = await sku_logic.create_sku(input)

        # Update the SKU
        update = UpdateSkuInput(
            id=created.id,
            name="Updated Test SKU",
        )
        updated = await sku_logic.update_sku(update)

        assert updated.id == created.id
        assert updated.code == created.code
        assert updated.name == "Updated Test SKU"
        assert updated.updated_at is not None

    async def test_update_sku_not_found_raises_error(self, sku_logic: SkuLogic) -> None:
        """Test that updating non-existent SKU raises NotFoundError."""
        update = UpdateSkuInput(
            id="non-existent-id",
            name="Updated Name",
        )

        with pytest.raises(NotFoundError, match="not found"):
            await sku_logic.update_sku(update)

    async def test_update_sku_duplicate_code_raises_error(self, sku_logic: SkuLogic) -> None:
        """Test that updating to duplicate code raises ConflictError."""
        # Create two SKUs
        input1 = CreateSkuInput(code="TEST-SKU-001", name="Test SKU 1")
        input2 = CreateSkuInput(code="TEST-SKU-002", name="Test SKU 2")

        _ = await sku_logic.create_sku(input1)
        sku2 = await sku_logic.create_sku(input2)

        # Try to update SKU 2 to have the same code as SKU 1
        update = UpdateSkuInput(
            id=sku2.id,
            code="TEST-SKU-001",
        )

        with pytest.raises(ConflictError, match="already exists"):
            await sku_logic.update_sku(update)

    async def test_delete_sku_success(self, sku_logic: SkuLogic) -> None:
        """Test successful SKU deletion."""
        # Create a SKU first
        input = CreateSkuInput(
            code="TEST-SKU-001",
            name="Test SKU",
        )
        created = await sku_logic.create_sku(input)

        # Delete the SKU
        await sku_logic.delete_sku(created.id)

        # Verify it's gone
        with pytest.raises(NotFoundError, match="not found"):
            await sku_logic.get_sku(created.id)

    async def test_delete_sku_not_found_raises_error(self, sku_logic: SkuLogic) -> None:
        """Test that deleting non-existent SKU raises NotFoundError."""
        with pytest.raises(NotFoundError, match="not found"):
            await sku_logic.delete_sku("non-existent-id")
