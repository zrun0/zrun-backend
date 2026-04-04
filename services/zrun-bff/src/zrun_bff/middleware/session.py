"""Session middleware for OAuth state storage.

Uses cookie-based sessions with cryptographic signing for security.
Sessions are stored client-side in cookies with HMAC signatures.
"""

from __future__ import annotations

from typing import Literal, Any

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request  # noqa: TC002
from starlette.responses import Response  # noqa: TC002
from starlette.types import ASGIApp  # noqa: TC002
from structlog import get_logger

logger = get_logger()

try:
    from itsdangerous import URLSafeSerializer
except ImportError:
    URLSafeSerializer = None  # type: ignore[assignment,misc]


class SessionMiddleware(BaseHTTPMiddleware):
    """Session middleware for storing session data in signed cookies.

    This middleware provides session support using cryptographically signed
    cookies. Session data is stored client-side but cannot be tampered with
    due to HMAC signing.

    Args:
        app: The ASGI application to wrap.
        secret_key: Secret key for signing session cookies.
        session_cookie: Name of the session cookie.
        max_age: Maximum age of session cookie in seconds.
        same_site: SameSite cookie policy.
        https_only: Whether to set Secure flag on cookies.
    """

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
        """Process request and add session support.

        Args:
            request: Incoming request.
            call_next: Next middleware or route handler.

        Returns:
            Response with session cookie set if session was modified.
        """
        # Load session from cookie
        session_data = self._load_session(request)

        # Attach session to request state
        request.state.session = session_data

        # Process request
        response = await call_next(request)

        # Save session if modified
        if self._session_modified(request.state.session, session_data):
            self._set_session_cookie(request.state.session, response)

        return response

    def _load_session(self, request: Request) -> dict[str, Any]:
        """Load session data from request cookie.

        Args:
            request: Incoming request.

        Returns:
            Session data dictionary. Empty if cookie is invalid or missing.
        """
        session_cookie = request.cookies.get(self._session_cookie)
        if not session_cookie:
            return {}

        try:
            decoded = self._serializer.loads(session_cookie)
            if isinstance(decoded, dict):
                return decoded
        except Exception as e:
            # Invalid signature or corrupted data, return empty session
            logger.warning("session_decode_failed", error=str(e))
            return {}

        return {}

    def _session_modified(
        self,
        new_session: dict[str, object],
        old_session: dict[str, object],
    ) -> bool:
        """Check if session data has been modified.

        Args:
            new_session: Current session data.
            old_session: Original session data.

        Returns:
            True if session has been modified.
        """
        return new_session != old_session

    def _set_session_cookie(
        self,
        session_data: dict[str, object],
        response: Response,
    ) -> None:
        """Set session cookie on response.

        Args:
            session_data: Session data to serialize.
            response: Response to set cookie on.
        """
        if not session_data:
            # Clear cookie if session is empty
            self._delete_cookie(response)
            return

        encoded = self._serializer.dumps(session_data)

        # Set cookie using Starlette's Response.set_cookie
        response.set_cookie(
            key=self._session_cookie,
            value=encoded,
            max_age=self._max_age,
            httponly=True,  # Prevent XSS
            secure=self._https_only,
            samesite=self._same_site,
            path="/",
        )

    def _delete_cookie(self, response: Response) -> None:
        """Delete session cookie.

        Args:
            response: Response to delete cookie from.
        """
        response.delete_cookie(
            key=self._session_cookie,
            path="/",
        )


def get_session(request: Request) -> dict[str, object]:
    """Get session from request state.

    This is a helper function to be used in route handlers.

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
