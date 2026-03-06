"""Business logic for SKU operations."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from zrun_core.errors import ConflictError, NotFoundError, ValidationError

if TYPE_CHECKING:
    from zrun_base.repository.sku import SkuRepository


@dataclass(frozen=True)
class SkuDomain:
    """SKU domain object.

    This represents a SKU in the domain layer, independent of
    any external concerns like gRPC or database schema.
    """

    id: str
    code: str
    name: str
    created_at: datetime
    updated_at: datetime | None = None

    def validate(self) -> None:
        """Validate the SKU domain object.

        Raises:
            ValidationError: If validation fails.
        """
        errors = []

        # Validate code format: [A-Z0-9-]{3,50}
        if not self.code or len(self.code) < 3 or len(self.code) > 50:
            errors.append("Code must be between 3 and 50 characters")

        # Check for invalid characters
        allowed_chars = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-")
        if not all(c in allowed_chars for c in self.code):
            errors.append("Code can only contain uppercase letters, numbers, and hyphens")

        # Validate name
        if not self.name or len(self.name.strip()) == 0:
            errors.append("Name is required")

        if len(self.name) > 200:
            errors.append("Name must not exceed 200 characters")

        if errors:
            raise ValidationError("; ".join(errors))


@dataclass(frozen=True)
class CreateSkuInput:
    """Input DTO for creating a SKU."""

    code: str
    name: str


@dataclass(frozen=True)
class UpdateSkuInput:
    """Input DTO for updating a SKU."""

    id: str
    code: str | None = None
    name: str | None = None


class SkuLogic:
    """Business logic for SKU operations.

    This class contains pure business rules and validation logic.
    It does not know about gRPC or database implementation details.
    """

    def __init__(self, repo: SkuRepository) -> None:
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
        # Validate input
        if not input.code or not input.code.strip():
            msg = "Code is required"
            raise ValidationError(msg)

        if not input.name or not input.name.strip():
            msg = "Name is required"
            raise ValidationError(msg)

        # Normalize code
        code = input.code.strip().upper()

        # Check for existing SKU with same code
        existing = await self._repo.get_by_code(code)
        if existing is not None:
            msg = f"SKU with code '{code}' already exists"
            raise ConflictError(msg)

        # Create domain object
        sku = SkuDomain(
            id=str(uuid.uuid4()),
            code=code,
            name=input.name.strip(),
            created_at=datetime.now(UTC),
        )

        # Validate
        sku.validate()

        # Persist
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
        if not sku_id or not sku_id.strip():
            msg = "SKU ID is required"
            raise ValidationError(msg)

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
        if not input.id or not input.id.strip():
            msg = "SKU ID is required"
            raise ValidationError(msg)

        # Get existing SKU
        existing = await self._repo.get_by_id(input.id)
        if existing is None:
            msg = f"SKU with ID '{input.id}' not found"
            raise NotFoundError(msg)

        # Prepare updates
        updates: dict[str, str] = {}
        if input.code is not None:
            code = input.code.strip().upper()
            if code != existing.code:
                # Check for conflict
                other = await self._repo.get_by_code(code)
                if other is not None and other.id != input.id:
                    msg = f"SKU with code '{code}' already exists"
                    raise ConflictError(msg)
                updates["code"] = code

        if input.name is not None:
            name = input.name.strip()
            if name:
                updates["name"] = name

        if not updates:
            return existing

        # Update domain object
        updated = SkuDomain(
            id=existing.id,
            code=updates.get("code", existing.code),
            name=updates.get("name", existing.name),
            created_at=existing.created_at,
            updated_at=datetime.now(UTC),
        )

        # Validate
        updated.validate()

        # Persist
        return await self._repo.update(updated)

    async def delete_sku(self, sku_id: str) -> None:
        """Delete a SKU.

        Args:
            sku_id: The SKU ID.

        Raises:
            ValidationError: If the SKU ID is invalid.
            NotFoundError: If the SKU does not exist.
        """
        if not sku_id or not sku_id.strip():
            msg = "SKU ID is required"
            raise ValidationError(msg)

        sku = await self._repo.get_by_id(sku_id)
        if sku is None:
            msg = f"SKU with ID '{sku_id}' not found"
            raise NotFoundError(msg)

        await self._repo.delete(sku_id)
