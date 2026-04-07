"""OAuth2 and JWT constants for BFF service."""

from enum import StrEnum


class GrantType(StrEnum):
    """OAuth2 grant types."""

    AUTHORIZATION_CODE = "authorization_code"
    REFRESH_TOKEN = "refresh_token"  # noqa: S105


class TokenType(StrEnum):
    """OAuth2 token types."""

    BEARER = "Bearer"


class OAuthScope(StrEnum):
    """Standard OAuth2 scopes."""

    OPENID = "openid"
    PROFILE = "profile"
    EMAIL = "email"

    @classmethod
    def default(cls) -> str:
        """Return default OAuth scope string."""
        return f"{cls.OPENID} {cls.PROFILE} {cls.EMAIL}"


class Scope(StrEnum):
    """Internal JWT scopes for microservices.

    Scopes are included in JWT tokens and checked by authorization dependencies.
    Format: resource:action (e.g., "pda:read" for PDA service read access).
    """

    # PDA service scopes
    PDA_READ = "pda:read"
    PDA_WRITE = "pda:write"

    # Web client scopes
    WEB_ADMIN = "web:admin"
    WEB_READ = "web:read"

    # Mini client scopes
    MINI_READ = "mini:read"

    # Admin scopes
    ADMIN_ALL = "admin:all"

    @classmethod
    def default(cls) -> str:
        """Return default internal scope string."""
        return f"{cls.PDA_READ} {cls.PDA_WRITE}"


class InternalTokenType(StrEnum):
    """Internal JWT token types for BFF service."""

    ACCESS = "access"
    REFRESH = "refresh"
