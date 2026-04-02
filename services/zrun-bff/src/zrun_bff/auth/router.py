"""OAuth2 authentication router for BFF service.

Implements OAuth2 flow with Casdoor and internal JWT re-issuance.
Architecture: Frontend -> BFF (OAuth2 with Casdoor) -> Internal JWT.
"""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

import httpx
from fastapi import APIRouter, HTTPException, Response, status
from fastapi.responses import RedirectResponse
from structlog import get_logger

if TYPE_CHECKING:
    from collections.abc import Mapping

from zrun_bff.config import BFFConfig
from zrun_bff.jwt import build_jwks, generate_token, get_public_key

logger = get_logger()

router = APIRouter()


@lru_cache
def get_config() -> BFFConfig:
    """Get cached BFF configuration.

    Returns:
        BFF configuration instance.
    """
    return BFFConfig()


@router.get("/auth/login")
async def login_redirect() -> RedirectResponse:
    """Redirect to Casdoor OAuth2 authorization endpoint.

    Returns:
        RedirectResponse to Casdoor login page.
    """
    config = get_config()
    auth_url = config.casdoor_authorize_url
    logger.info("oauth_login_redirect", url=auth_url)
    return RedirectResponse(url=auth_url, status_code=status.HTTP_302_FOUND)


@router.get("/auth/callback")
async def oauth_callback(
    code: str,
    state: str | None = None,
) -> Response:
    """OAuth2 callback endpoint.

    Exchanges authorization code for Casdoor token, validates it,
    and issues an internal JWT for microservices.

    Args:
        code: Authorization code from Casdoor.
        state: OAuth2 state parameter for CSRF protection (future use).

    Returns:
        Response with internal JWT token in body.

    Raises:
        HTTPException: If token exchange fails or Casdoor token is invalid.
    """
    config = get_config()

    # Log state parameter for CSRF protection (future validation)
    if state:
        logger.debug("oauth_callback_with_state", state=state)

    # Exchange authorization code for Casdoor token
    async with httpx.AsyncClient() as client:
        try:
            token_response = await client.post(
                config.casdoor_token_endpoint,
                data={
                    "grant_type": "authorization_code",
                    "client_id": config.casdoor_client_id,
                    "client_secret": config.casdoor_client_secret,
                    "code": code,
                    "redirect_uri": config.casdoor_redirect_uri,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            token_response.raise_for_status()
        except httpx.HTTPStatusError as e:
            logger.error("casdoor_token_exchange_failed", status=e.response.status_code)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Failed to exchange authorization code",
            ) from e

        token_data = token_response.json()

    # Validate Casdoor token and extract user info
    # For now, we trust Casdoor and extract user ID from the token
    # In production, you may want to validate the Casdoor JWT signature
    access_token = token_data.get("access_token")
    if not access_token:
        logger.error("casdoor_token_missing_access_token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Casdoor token response",
        )

    # Extract user ID from Casdoor token
    # Casdoor token contains user info in JWT format
    # For simplicity, we decode without signature verification (trusted Casdoor)
    # In production, verify signature using Casdoor JWKS
    from jose import jwt as jose_jwt

    try:
        casdoor_payload = jose_jwt.get_unverified_claims(access_token)
    except Exception as e:
        logger.error("casdoor_token_decode_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Failed to decode Casdoor token",
        ) from e

    user_id = casdoor_payload.get("sub")
    if not user_id:
        logger.error("casdoor_token_missing_sub")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Casdoor token missing subject claim",
        )

    # Generate internal JWT for microservices
    try:
        internal_token = generate_token(
            private_key=config.jwt_private_key,
            issuer=config.jwt_issuer,
            audience=config.jwt_audience,
            subject=user_id,
            expiration_seconds=config.jwt_expiration_seconds,
            key_id=config.jwt_key_id,
            additional_claims={
                "scope": "pda:read pda:write",  # Default scopes, can be customized
            },
        )
        logger.info("internal_jwt_issued", sub=user_id)
    except ValueError as e:
        logger.error("internal_jwt_generation_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate internal token",
        ) from e

    # Return internal JWT token
    # In production, set as HttpOnly cookie or return in body
    return Response(
        content=f'{{"access_token":"{internal_token}","token_type":"Bearer"}}',
        status_code=status.HTTP_200_OK,
        media_type="application/json",
    )


@router.get("/.well-known/jwks.json")
async def jwks_endpoint() -> Mapping[str, object]:
    """JWKS endpoint for internal services.

    Exposes public key for JWT verification. Internal services use this
    endpoint to validate internal JWTs issued by BFF.

    Returns:
        JWKS dictionary with keys list.

    Security:
        - Only contains public key, never private key
        - Caching recommended (TTL 300s)
    """
    config = get_config()

    try:
        public_key = get_public_key(config.jwt_private_key)
        jwks = build_jwks(public_key, config.jwt_key_id)
        logger.debug("jwks_served", keys_count=len(jwks["keys"]))
        return jwks
    except ValueError as e:
        logger.error("jwks_generation_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate JWKS",
        ) from e
