"""BFF service configuration."""

from __future__ import annotations

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
    casdoor_client_secret: str = ""
    casdoor_redirect_uri: str = "http://localhost:8000/auth/callback"
    casdoor_authorization_endpoint: str = "http://localhost:8080/api/oauth/authorize"
    casdoor_token_endpoint: str = "http://localhost:8080/api/oauth/token"

    # JWT Signing Configuration
    jwt_private_key_path: str = ""
    jwt_key_id: str = "key-1"  # JWKS key ID for rotation support
    jwt_key_version: str = "v1"  # Key version for rotation tracking
    jwt_issuer: str = "zrun-bff"
    jwt_audience: str = "zrun-services"
    jwt_expiration_seconds: int = 3600

    # API Configuration
    api_prefix: str = "/api"
    cors_origins: list[str] = ["http://localhost:3000"]

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
    def casdoor_authorize_url(self) -> str:
        """Generate Casdoor authorization URL.

        Returns:
            Full authorization URL with client_id and redirect_uri.
        """
        from urllib.parse import urlencode

        params = {
            "client_id": self.casdoor_client_id,
            "redirect_uri": self.casdoor_redirect_uri,
            "response_type": "code",
            "scope": "openid profile email",
        }
        return f"{self.casdoor_authorization_endpoint}?{urlencode(params)}"
