"""PDA SKU API routes.

Example API routes demonstrating how to use gRPC clients
in the BFF service.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from structlog import get_logger

if TYPE_CHECKING:
    from zrun_bff.clients.base import BaseSkuClient

from zrun_bff.clients.dependencies import get_sku_client
from zrun_bff.errors import (
    NotFoundError,
)

logger = get_logger()

router = APIRouter(prefix="/api/pda/skus", tags=["PDA", "SKU"])


# Request/Response schemas
class CreateSkuRequest(BaseModel):
    """Request schema for creating a SKU."""

    code: str = Field(..., min_length=1, max_length=64, description="Unique SKU code")
    name: str = Field(..., min_length=1, max_length=255, description="SKU display name")


class SkuResponse(BaseModel):
    """Response schema for SKU data."""

    id: str
    code: str
    name: str


class SkuListResponse(BaseModel):
    """Response schema for SKU list."""

    items: list[SkuResponse]
    next_page_token: str


@router.post("", response_model=dict[str, str])
async def create_sku(
    request: CreateSkuRequest,
    client: BaseSkuClient = Depends(get_sku_client),
) -> dict[str, str]:
    """Create a new SKU.

    Args:
        request: SKU creation request.
        client: SKU service client (injected).

    Returns:
        Created SKU ID.

    Raises:
        ValidationError: If request validation fails.
        ConflictError: If SKU already exists.
        InternalError: If SKU creation fails.
    """
    result = await client.create_sku(
        code=request.code,
        name=request.name,
    )
    logger.info("sku_created_api", id=result["id"], code=request.code)
    return {"id": result["id"], "code": result["code"]}


@router.get("/{sku_id}", response_model=SkuResponse)
async def get_sku(
    sku_id: str,
    client: BaseSkuClient = Depends(get_sku_client),
) -> SkuResponse:
    """Get SKU by ID.

    Args:
        sku_id: SKU internal ID.
        client: SKU service client (injected).

    Returns:
        SKU data.

    Raises:
        ValidationError: If SKU ID is invalid.
        NotFoundError: If SKU not found.
        InternalError: If SKU fetch fails.
    """
    result = await client.get_sku(sku_id)
    if result is None:
        raise NotFoundError(detail=f"SKU {sku_id} not found")
    return SkuResponse(**result)


@router.get("", response_model=SkuListResponse)
async def list_skus(
    page_size: int = 50,
    page_token: str = "",
    client: BaseSkuClient = Depends(get_sku_client),
) -> SkuListResponse:
    """List SKUs with pagination.

    Args:
        page_size: Number of items per page.
        page_token: Pagination token.
        client: SKU service client (injected).

    Returns:
        Paginated SKU list.

    Raises:
        ValidationError: If pagination parameters are invalid.
        ServiceUnavailableError: If SKU service is unavailable.
        InternalError: If SKU list fails.
    """
    result = await client.list_skus(
        page_size=page_size,
        page_token=page_token,
    )
    return SkuListResponse(**result)
