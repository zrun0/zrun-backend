"""Domain objects for SKU operations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from zrun_core.domain import ValidationError

if TYPE_CHECKING:
    from datetime import datetime


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


__all__ = [
    "SkuDomain",
    "CreateSkuInput",
    "UpdateSkuInput",
]
