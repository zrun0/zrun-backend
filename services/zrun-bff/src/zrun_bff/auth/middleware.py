"""User context middleware for automatic authentication context propagation.

This middleware automatically extracts user information from JWT tokens
and sets the user context for gRPC client calls, eliminating the need
for manual context setup in each endpoint.

Architecture:
    1. Extract JWT from Authorization header
    2. Validate and decode token
    3. Set user context via ContextVar
    4. Propagate context to gRPC calls via interceptors

Usage:
    app.add_middleware(UserContextMiddleware)
"""

from __future__ import annotations

from typing import Any, Literal

from jose import JWTError
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp
from structlog import get_logger

from zrun_bff.auth.verification import verify_jwt_with_config
from zrun_bff.clients.interceptors import set_user_context
from zrun_bff.config import BFFConfig, get_config

logger = get_logger()


class UserContextMiddleware(BaseHTTPMiddleware):
    """Middleware for automatic user context propagation.

    This middleware:
    - Extracts and validates JWT from Authorization header
    - Sets user context for downstream gRPC calls
    - Handles authentication failures gracefully

    The middleware is non-blocking: if authentication fails, the request
    continues without user context (allowing anonymous endpoints).
    Protected endpoints should use require_scope() dependency.

    Args:
        app: The ASGI application to wrap.
        optional: If True, authentication failures don't block requests.
                   If False, unauthenticated requests are rejected. Default: True.
    """

    def __init__(
        self,
        app: ASGIApp,
        optional: bool = True,
        config: BFFConfig | None = None,
    ) -> None:
        """Initialize user context middleware.

        Args:
            app: The ASGI application.
            optional: If True, auth failures don't block. If False,
                     unauthenticated requests get 401. Default: True.
            config: BFF configuration. If None, uses cached config from get_config().
        """
        super().__init__(app)
        self._optional = optional
        self._config = config or get_config()

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        """Process request and set user context.

        Args:
            request: Incoming request.
            call_next: Next middleware or route handler.

        Returns:
            Response from downstream handler.
        """
        # Try to extract and validate token
        user_context = self._extract_user_context(request)

        if user_context:
            # Set context for gRPC calls
            set_user_context(
                user_id=user_context["user_id"],
                token=user_context["token"],
                scopes=user_context.get("scopes"),
            )
            logger.debug(
                "user_context_set",
                user_id=user_context["user_id"][:8] + "...",  # Log prefix only
                scopes=user_context.get("scopes"),
            )
        elif not self._optional:
            # Reject unauthenticated requests if not optional.
            # Must return a Response directly — raising HTTPException inside
            # BaseHTTPMiddleware.dispatch() bypasses FastAPI exception handlers.
            logger.warning("auth_required_no_token")
            return JSONResponse(
                status_code=401,
                content={"detail": "Authentication required"},
                headers={"WWW-Authenticate": "Bearer"},
            )

        response = await call_next(request)
        return response

    def _extract_user_context(self, request: Request) -> dict[str, Any] | None:
        """Extract and validate user context from JWT token.

        Args:
            request: Incoming request.

        Returns:
            User context dict with user_id, token, and scopes, or None.
        """
        # Extract Authorization header
        auth_header = request.headers.get("authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return None

        token = auth_header.split(" ", 1)[1].strip()
        if not token:
            return None

        # Validate token using public key
        try:
            payload = verify_jwt_with_config(token, self._config)

            # Extract user context
            user_id = payload.get("sub")
            if not isinstance(user_id, str):
                logger.warning("auth_invalid_sub", sub_type=type(user_id).__name__)
                return None

            scope_claim = payload.get("scope", "")
            scopes = scope_claim.split() if isinstance(scope_claim, str) else []

            return {
                "user_id": user_id,
                "token": token,
                "scopes": scopes,
            }

        except JWTError as e:
            logger.warning("auth_token_validation_failed", error=str(e))
            return None
        except Exception as e:
            logger.error("auth_context_extraction_failed", error=str(e))
            return None


# ---------------------------------------------------------------------------
# Session middleware (moved from middleware/session.py)
# ---------------------------------------------------------------------------

try:
    from itsdangerous import URLSafeSerializer
except ImportError:
    URLSafeSerializer = None  # type: ignore[assignment,misc]


class SessionMiddleware(BaseHTTPMiddleware):
    """Session middleware for storing session data in signed cookies.

    Uses cryptographically signed cookies (HMAC). Session data is stored
    client-side and cannot be tampered with.

    Args:
        app: The ASGI application to wrap.
        secret_key: Secret key for signing session cookies.
        session_cookie: Name of the session cookie.
        max_age: Maximum age of session cookie in seconds.
        same_site: SameSite cookie policy.
        https_only: Whether to set Secure flag on cookies.
    """

    _same_site: Literal["lax", "strict", "none"]

    def __init__(
        self,
        app: ASGIApp,
        secret_key: str,
        session_cookie: str = "session",
        max_age: int = 14 * 24 * 60 * 60,  # 14 days
        same_site: Literal["lax", "strict", "none"] = "lax",
        https_only: bool = False,
    ) -> None:
        super().__init__(app)
        if URLSafeSerializer is None:
            msg = (
                "itsdangerous is required for SessionMiddleware. "
                "Install with: pip install itsdangerous"
            )
            raise ImportError(msg)

        self._serializer = URLSafeSerializer(secret_key)
        self._session_cookie = session_cookie
        self._max_age = max_age
        self._same_site = same_site
        self._https_only = https_only

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        session_data = self._load_session(request)
        request.state.session = session_data
        response = await call_next(request)
        if self._session_modified(request.state.session, session_data):
            self._set_session_cookie(request.state.session, response)
        return response

    def _load_session(self, request: Request) -> dict[str, Any]:
        session_cookie = request.cookies.get(self._session_cookie)
        if not session_cookie:
            return {}
        try:
            decoded = self._serializer.loads(session_cookie)
            if isinstance(decoded, dict):
                return decoded
        except Exception as e:
            logger.warning("session_decode_failed", error=str(e))
        return {}

    def _session_modified(
        self,
        new_session: dict[str, object],
        old_session: dict[str, object],
    ) -> bool:
        return new_session != old_session

    def _set_session_cookie(
        self,
        session_data: dict[str, object],
        response: Response,
    ) -> None:
        if not session_data:
            self._delete_cookie(response)
            return
        encoded = self._serializer.dumps(session_data)
        response.set_cookie(
            key=self._session_cookie,
            value=encoded,
            max_age=self._max_age,
            httponly=True,
            secure=self._https_only,
            samesite=self._same_site,
            path="/",
        )

    def _delete_cookie(self, response: Response) -> None:
        response.delete_cookie(key=self._session_cookie, path="/")


def get_session(request: Request) -> dict[str, object]:
    """Get session from request state.

    Args:
        request: FastAPI request with session middleware.

    Returns:
        Session data dictionary.

    Raises:
        RuntimeError: If session middleware is not configured.
    """
    if not hasattr(request.state, "session"):
        msg = "SessionMiddleware not configured. Add SessionMiddleware to your FastAPI app."
        raise RuntimeError(msg)
    return request.state.session


__all__ = ["UserContextMiddleware", "SessionMiddleware", "get_session"]
