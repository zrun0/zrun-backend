"""OAuth2 authentication router for BFF service.

Implements OAuth2 flow with Casdoor and internal JWT re-issuance.
Architecture: Frontend -> BFF (OAuth2 with Casdoor) -> Internal JWT.
"""

from __future__ import annotations

import secrets
from collections.abc import Mapping
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel
from structlog import get_logger

from zrun_bff.auth.constants import GrantType, TokenType
from zrun_bff.auth.tokens import TokenPair, generate_token_pair, refresh_access_token
from zrun_bff.auth.casdoor import verify_casdoor_token_async
from zrun_bff.config import BFFConfig, get_config
from zrun_bff.errors import UnauthorizedError
from zrun_core.auth import build_jwks, get_public_key
from zrun_bff.auth.middleware import get_session

logger = get_logger()


class TokenRefreshRequest(BaseModel):
    """Request model for token refresh."""

    refresh_token: str


class TokenResponse(BaseModel):
    """Token response for OAuth callback and refresh endpoints."""

    access_token: str
    refresh_token: str
    expires_in: int
    token_type: TokenType = TokenType.BEARER

    @classmethod
    def from_token_pair(cls, token_pair: TokenPair) -> TokenResponse:
        """Create TokenResponse from TokenPair."""
        return cls(
            access_token=token_pair.access_token,
            refresh_token=token_pair.refresh_token,
            expires_in=token_pair.expires_in,
            token_type=token_pair.token_type,
        )


router = APIRouter()


@router.get("/auth/login")
async def login_redirect(
    request: Request,
    config: BFFConfig = Depends(get_config),
) -> RedirectResponse:
    """Redirect to Casdoor OAuth2 authorization endpoint.

    Generates a secure state parameter for CSRF protection and stores
    it in the session. The state is verified in the callback endpoint.

    Args:
        request: FastAPI request object.
        config: BFF configuration.

    Returns:
        RedirectResponse to Casdoor login page with state parameter.
    """

    # Generate cryptographically secure state parameter
    state = secrets.token_urlsafe(config.oauth_state_bytes)

    # Store state in session for verification in callback
    session = get_session(request)
    session["oauth_state"] = state

    # Build authorization URL with state parameter
    params = {
        "client_id": config.casdoor_client_id,
        "redirect_uri": config.casdoor_redirect_uri,
        "response_type": "code",
        "scope": config.oauth_scope,
        "state": state,  # CSRF protection
    }
    auth_url = f"{config.casdoor_authorization_endpoint}?{urlencode(params)}"

    logger.info("oauth_login_redirect", state=state[:8] + "...")  # Log prefix only
    return RedirectResponse(url=auth_url, status_code=status.HTTP_302_FOUND)


@router.get("/auth/callback")
async def oauth_callback(
    request: Request,
    code: str,
    state: str | None = None,
    config: BFFConfig = Depends(get_config),
) -> Response:
    """OAuth2 callback endpoint.

    Exchanges authorization code for Casdoor token, validates it,
    and issues an internal JWT for microservices.

    Args:
        request: FastAPI request object.
        code: Authorization code from Casdoor.
        state: OAuth2 state parameter for CSRF protection.
        config: BFF configuration.

    Returns:
        Response with internal JWT token in body.

    Raises:
        HTTPException: If token exchange fails or Casdoor token is invalid.
    """

    # Verify state parameter for CSRF protection
    session = get_session(request)
    stored_state = session.pop("oauth_state", None)

    if stored_state is None:
        logger.error("oauth_callback_missing_state", state_provided=state is not None)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing state parameter. Session may have expired.",
        )

    if state != stored_state:
        expected = str(stored_state)[:8] + "..." if isinstance(stored_state, str) else "..."
        received = str(state)[:8] + "..." if isinstance(state, str) else None
        logger.error(
            "oauth_callback_state_mismatch",
            expected=expected,
            received=received,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid state parameter. Possible CSRF attack.",
        )

    state_prefix = str(state)[:8] + "..." if isinstance(state, str) else "..."
    logger.info("oauth_callback_state_valid", state=state_prefix)

    # Exchange authorization code for Casdoor token
    # Use shared HTTP client from app state for connection pooling
    client: httpx.AsyncClient = request.app.state.http_client
    try:
        token_response = await client.post(
            config.casdoor_token_endpoint,
            data={
                "grant_type": GrantType.AUTHORIZATION_CODE,
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
    access_token = token_data.get("access_token")
    if not access_token:
        logger.error("casdoor_token_missing_access_token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Casdoor token response",
        )

    # Verify Casdoor token signature using JWKS
    try:
        casdoor_payload = await verify_casdoor_token_async(access_token, config)
    except ValueError as e:
        logger.error("casdoor_token_verification_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Failed to verify Casdoor token: {e}",
        ) from e

    user_id = casdoor_payload.get("sub")
    if not isinstance(user_id, str):
        logger.error("casdoor_token_missing_sub")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Casdoor token missing subject claim",
        )

    # Generate token pair (access + refresh)
    try:
        token_pair = generate_token_pair(
            config=config,
            user_id=user_id,
            scopes=config.default_scopes,
        )
        logger.info("token_pair_issued", sub=user_id)
    except ValueError as e:
        logger.error("token_pair_generation_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate token pair",
        ) from e

    # Return token pair
    return JSONResponse(
        content=TokenResponse.from_token_pair(token_pair).model_dump(),
    )


@router.post("/auth/refresh")
async def refresh_token(
    request: TokenRefreshRequest,
    config: BFFConfig = Depends(get_config),
) -> JSONResponse:
    """Refresh access token using refresh token.

    Implements token rotation: the old refresh token is invalidated
    and a new token pair is issued.

    Args:
        request: Refresh token request.
        config: BFF configuration.

    Returns:
        JSON response with new access and refresh tokens.

    Raises:
        UnauthorizedError: If refresh token is invalid or expired.
    """

    # Generate new token pair
    try:
        token_pair = refresh_access_token(
            config=config,
            refresh_token=request.refresh_token,
        )
        logger.info("token_pair_refreshed")
    except ValueError as e:
        logger.error("refresh_token_failed", error=str(e))
        raise UnauthorizedError(detail=str(e)) from e

    # Return new token pair
    return JSONResponse(
        content=TokenResponse.from_token_pair(token_pair).model_dump(),
    )


@router.get("/.well-known/jwks.json")
async def jwks_endpoint(
    config: BFFConfig = Depends(get_config),
) -> Mapping[str, object]:
    """JWKS endpoint for internal services.

    Exposes public key for JWT verification. Internal services use this
    endpoint to validate internal JWTs issued by BFF.

    Args:
        config: BFF configuration.

    Returns:
        JWKS dictionary with keys list.

    Security:
        - Only contains public key, never private key
        - Caching recommended (TTL 300s)
    """

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
