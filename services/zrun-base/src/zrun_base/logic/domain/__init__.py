"""Domain objects for SKU operations."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from zrun_core.errors import ValidationError

if TYPE_CHECKING:
    from datetime import datetime

# Pre-compiled regex for SKU code validation: [A-Z0-9-]{3,50}
_SKU_CODE_PATTERN = re.compile(r"^[A-Z0-9-]{3,50}$")
# Maximum name length constant
_MAX_NAME_LENGTH = 200


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

        if not _SKU_CODE_PATTERN.match(self.code):
            errors.append(
                "Code must be between 3 and 50 characters and contain only "
                "uppercase letters, numbers, and hyphens"
            )

        if not self.name or len(self.name.strip()) == 0:
            errors.append("Name is required")

        if len(self.name) > _MAX_NAME_LENGTH:
            errors.append(f"Name must not exceed {_MAX_NAME_LENGTH} characters")

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
