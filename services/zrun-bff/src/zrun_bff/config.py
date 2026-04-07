"""BFF service configuration."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import SettingsConfigDict

from zrun_core.infra import ServiceConfig


class BFFConfig(ServiceConfig):
    """Configuration for BFF service.

    Extends ServiceConfig with OAuth2 and JWT signing settings.

    Environment variables:
        CASDOOR_CLIENT_ID: Casdoor OAuth2 client ID
        CASDOOR_CLIENT_SECRET: Casdoor OAuth2 client secret
        CASDOOR_REDIRECT_URI: OAuth2 callback URL
        CASDOOR_AUTHORIZATION_ENDPOINT: Casdoor authorize URL
        CASDOOR_TOKEN_ENDPOINT: Casdoor token endpoint
        JWT_PRIVATE_KEY_PATH: Path to JWT signing private key
        JWT_ISSUER: JWT issuer claim (default: zrun-bff)
        JWT_AUDIENCE: JWT audience claim (default: zrun-services)
        JWT_EXPIRATION_SECONDS: Internal JWT TTL in seconds (default: 3600)
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Casdoor OAuth2 Configuration
    casdoor_client_id: str = ""
    casdoor_client_secret: str = ""  # noqa: S105
    casdoor_redirect_uri: str = "http://localhost:8000/auth/callback"
    casdoor_authorization_endpoint: str = "http://localhost:8080/api/oauth/authorize"
    casdoor_token_endpoint: str = "http://localhost:8080/api/oauth/token"  # noqa: S105

    # OAuth2 Settings
    oauth_state_bytes: int = 32  # Cryptographically secure state parameter size
    oauth_scope: str = "openid profile email"  # OAuth2 scope for Casdoor
    default_scopes: str = "pda:read pda:write"  # Default scopes for internal JWT

    # Note: oauth_scope and default_scopes use string literals for pydantic-settings compatibility.
    # Use OAuthScope.default() and InternalScope.default() from constants module in code.

    # JWT Signing Configuration
    jwt_private_key_path: str = ""
    jwt_public_key_path: str = ""  # Path to public key for token verification
    jwt_key_id: str = "key-1"  # JWKS key ID for rotation support
    jwt_key_version: str = "v1"  # Key version for rotation tracking
    jwt_issuer: str = "zrun-bff"
    jwt_audience: str = "zrun-services"
    jwt_expiration_seconds: int = 3600  # 1 hour
    jwt_refresh_expiration_seconds: int = 2592000  # 30 days

    # API Configuration
    api_prefix: str = "/api"
    cors_origins: list[str] = ["http://localhost:3000"]

    # Session Configuration
    session_secret_key: str = "change-this-in-production"  # noqa: S105

    # gRPC Service URLs
    base_service_url: str = "localhost:50051"
    ops_service_url: str = "localhost:50052"
    stock_service_url: str = "localhost:50053"

    @property
    def jwt_private_key(self) -> str:
        """Read and return JWT private key content.

        Returns:
            Private key content as string.
        """
        if not self.jwt_private_key_path:
            msg = "JWT_PRIVATE_KEY_PATH not configured"
            raise RuntimeError(msg)

        path = Path(self.jwt_private_key_path)
        if not path.exists():
            msg = f"JWT private key not found: {self.jwt_private_key_path}"
            raise FileNotFoundError(msg)

        return path.read_text()

    @property
    def jwt_public_key(self) -> str:
        """Read and return JWT public key content.

        Returns:
            Public key content as string.
        """
        if not self.jwt_public_key_path:
            # Fallback: derive public key from private key
            from zrun_core.auth import get_public_key_pem

            return get_public_key_pem(self.jwt_private_key)

        path = Path(self.jwt_public_key_path)
        if not path.exists():
            msg = f"JWT public key not found: {self.jwt_public_key_path}"
            raise FileNotFoundError(msg)

        return path.read_text()

    @property
    def casdoor_authorize_url(self) -> str:
        """Generate Casdoor authorization URL.

        Returns:
            Full authorization URL with client_id and redirect_uri.
        """
        from urllib.parse import urlencode

        from zrun_bff.auth.constants import OAuthScope

        params = {
            "client_id": self.casdoor_client_id,
            "redirect_uri": self.casdoor_redirect_uri,
            "response_type": "code",
            "scope": OAuthScope.default(),
        }
        return f"{self.casdoor_authorization_endpoint}?{urlencode(params)}"


@lru_cache
def get_config() -> BFFConfig:
    """Get cached BFF configuration instance.

    This is the centralized configuration getter for the entire BFF service.
    All other modules should import and use this function instead of
    defining their own get_config() wrappers.

    Returns:
        Cached BFFConfig instance loaded from environment.

    Example:
        >>> from zrun_bff.config import get_config
        >>> config = get_config()
        >>> print(config.casdoor_client_id)
    """
    return BFFConfig()
