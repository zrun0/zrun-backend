"""Business logic for SKU operations."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from zrun_base.logic.domain import CreateSkuInput, SkuDomain, UpdateSkuInput
from zrun_core.errors import ConflictError, NotFoundError, ValidationError

if TYPE_CHECKING:
    from zrun_base.repository.protocols import SkuRepositoryProtocol


def _normalize_code(code: str) -> str:
    """Normalize SKU code by stripping whitespace and converting to uppercase.

    Args:
        code: The raw SKU code.

    Returns:
        The normalized code.
    """
    return code.strip().upper()


def _validate_non_empty_string(value: str | None, field_name: str) -> str:
    """Validate that a string is non-empty after stripping whitespace.

    Args:
        value: The string value to validate.
        field_name: The name of the field for error messages.

    Returns:
        The stripped string value.

    Raises:
        ValidationError: If the value is empty or None.
    """
    if not value or not value.strip():
        msg = f"{field_name} is required"
        raise ValidationError(msg)
    return value.strip()


class SkuLogic:
    """Business logic for SKU operations.

    This class contains pure business rules and validation logic.
    It does not know about gRPC or database implementation details.
    """

    def __init__(self, repo: SkuRepositoryProtocol) -> None:
        """Initialize the SKU logic.

        Args:
            repo: SKU repository for persistence operations.
        """
        self._repo = repo

    async def create_sku(self, input: CreateSkuInput) -> SkuDomain:
        """Create a new SKU.

        Args:
            input: Input data for creating the SKU.

        Returns:
            The created SKU domain object.

        Raises:
            ValidationError: If validation fails.
            ConflictError: If a SKU with the same code already exists.
        """
        code = _normalize_code(_validate_non_empty_string(input.code, "Code"))
        name = _validate_non_empty_string(input.name, "Name")

        existing = await self._repo.get_by_code(code)
        if existing is not None:
            msg = f"SKU with code '{code}' already exists"
            raise ConflictError(msg)

        sku = SkuDomain(
            id=str(uuid.uuid4()),
            code=code,
            name=name,
            created_at=datetime.now(UTC),
        )

        sku.validate()

        return await self._repo.create(sku)

    async def get_sku(self, sku_id: str) -> SkuDomain:
        """Get a SKU by ID.

        Args:
            sku_id: The SKU ID.

        Returns:
            The SKU domain object.

        Raises:
            ValidationError: If the SKU ID is invalid.
            NotFoundError: If the SKU does not exist.
        """
        _validate_non_empty_string(sku_id, "SKU ID")

        sku = await self._repo.get_by_id(sku_id)
        if sku is None:
            msg = f"SKU with ID '{sku_id}' not found"
            raise NotFoundError(msg)

        return sku

    async def update_sku(self, input: UpdateSkuInput) -> SkuDomain:
        """Update an existing SKU.

        Args:
            input: Input data for updating the SKU.

        Returns:
            The updated SKU domain object.

        Raises:
            ValidationError: If validation fails.
            NotFoundError: If the SKU does not exist.
            ConflictError: If the new code conflicts with another SKU.
        """
        sku_id = _validate_non_empty_string(input.id, "SKU ID")

        existing = await self._repo.get_by_id(sku_id)
        if existing is None:
            msg = f"SKU with ID '{sku_id}' not found"
            raise NotFoundError(msg)

        updates: dict[str, str] = {}
        if input.code is not None:
            code = _normalize_code(input.code)
            if code != existing.code:
                other = await self._repo.get_by_code(code)
                if other is not None and other.id != sku_id:
                    msg = f"SKU with code '{code}' already exists"
                    raise ConflictError(msg)
                updates["code"] = code

        if input.name is not None:
            name = _validate_non_empty_string(input.name, "Name")
            if name:
                updates["name"] = name

        if not updates:
            return existing

        updated = SkuDomain(
            id=existing.id,
            code=updates.get("code", existing.code),
            name=updates.get("name", existing.name),
            created_at=existing.created_at,
            updated_at=datetime.now(UTC),
        )

        updated.validate()

        return await self._repo.update(updated)

    async def delete_sku(self, sku_id: str) -> None:
        """Delete a SKU.

        Args:
            sku_id: The SKU ID.

        Raises:
            ValidationError: If the SKU ID is invalid.
            NotFoundError: If the SKU does not exist.
        """
        _validate_non_empty_string(sku_id, "SKU ID")

        sku = await self._repo.get_by_id(sku_id)
        if sku is None:
            msg = f"SKU with ID '{sku_id}' not found"
            raise NotFoundError(msg)

        await self._repo.delete(sku_id)
