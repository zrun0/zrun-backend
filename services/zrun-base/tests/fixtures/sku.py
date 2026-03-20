"""Test data fixtures for SKU tests."""

from __future__ import annotations

from datetime import UTC, datetime

from zrun_base.logic.domain import CreateSkuInput, SkuDomain, UpdateSkuInput


def create_test_sku(
    sku_id: str = "test-sku-id",
    code: str = "TEST-SKU-001",
    name: str = "Test SKU",
    created_at: datetime | None = None,
) -> SkuDomain:
    """Create a test SKU domain object.

    Args:
        sku_id: The SKU ID.
        code: The SKU code.
        name: The SKU name.
        created_at: The creation timestamp.

    Returns:
        A SkuDomain object.
    """
    return SkuDomain(
        id=sku_id,
        code=code,
        name=name,
        created_at=created_at or datetime.now(UTC),
    )


def create_create_sku_input(
    code: str = "TEST-SKU-001",
    name: str = "Test SKU",
) -> CreateSkuInput:
    """Create a CreateSkuInput DTO.

    Args:
        code: The SKU code.
        name: The SKU name.

    Returns:
        A CreateSkuInput object.
    """
    return CreateSkuInput(code=code, name=name)


def create_update_sku_input(
    sku_id: str = "test-sku-id",
    code: str | None = None,
    name: str | None = None,
) -> UpdateSkuInput:
    """Create an UpdateSkuInput DTO.

    Args:
        sku_id: The SKU ID.
        code: The new code (optional).
        name: The new name (optional).

    Returns:
        An UpdateSkuInput object.
    """
    return UpdateSkuInput(id=sku_id, code=code, name=name)
