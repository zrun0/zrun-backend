"""SQLAlchemy 2.0 SKU model."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from zrun_core.infra import Base, TimestampMixin

if TYPE_CHECKING:
    from zrun_base.logic.domain import SkuDomain


class SkuModel(Base, TimestampMixin):
    """SQLAlchemy model for SKU table.

    This model represents the skus table in the database.
    It follows SQLAlchemy 2.0 modern declarative syntax.

    Architecture Note:
        This model lives in the Repository layer and should NOT be
        imported by the Logic layer. The Logic layer only works with
        frozen SkuDomain dataclass objects.
    """

    __tablename__ = "skus"

    # Primary key - TEXT for UUIDs
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
    )

    # Unique business key
    code: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
    )

    # Name field
    name: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    def to_domain(self) -> SkuDomain:
        """Convert model to domain object.

        This method encapsulates the conversion logic, keeping it
        close to the model definition.

        Returns:
            SkuDomain frozen dataclass.
        """
        from zrun_base.logic.domain import SkuDomain

        return SkuDomain(
            id=self.id,
            code=self.code,
            name=self.name,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )

    @classmethod
    def from_domain(cls, sku: SkuDomain) -> SkuModel:
        """Create model from domain object.

        Args:
            sku: Domain object.

        Returns:
            SQLAlchemy model instance.
        """
        return cls(
            id=sku.id,
            code=sku.code,
            name=sku.name,
            created_at=sku.created_at,
            # updated_at is managed by TimestampMixin, not passed from domain
        )
