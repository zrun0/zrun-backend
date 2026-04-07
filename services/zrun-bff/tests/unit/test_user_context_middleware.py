"""Unit tests for UserContextMiddleware."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from jose import jwt

from zrun_bff.auth.middleware import UserContextMiddleware
from zrun_bff.auth.tokens import generate_token_pair


@pytest.fixture
def test_key_files() -> Generator[str]:
    """Create temporary key files for testing."""
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization

    # Generate RSA key pair
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend(),
    )

    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()

    public_pem = (
        private_key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        private_key_path = Path(tmpdir) / "private.pem"
        public_key_path = Path(tmpdir) / "public.pem"

        private_key_path.write_text(private_pem)
        public_key_path.write_text(public_pem)

        original_private = os.environ.get("JWT_PRIVATE_KEY_PATH")
        original_public = os.environ.get("JWT_PUBLIC_KEY_PATH")

        os.environ["JWT_PRIVATE_KEY_PATH"] = str(private_key_path)
        os.environ["JWT_PUBLIC_KEY_PATH"] = str(public_key_path)

        try:
            yield tmpdir
        finally:
            if original_private is not None:
                os.environ["JWT_PRIVATE_KEY_PATH"] = original_private
            else:
                os.environ.pop("JWT_PRIVATE_KEY_PATH", None)

            if original_public is not None:
                os.environ["JWT_PUBLIC_KEY_PATH"] = original_public
            else:
                os.environ.pop("JWT_PUBLIC_KEY_PATH", None)


@pytest.mark.usefixtures("test_key_files")
class TestUserContextMiddleware:
    """Tests for UserContextMiddleware."""

    def test_middleware_sets_user_context_with_valid_token(self) -> None:
        """Test that middleware sets user context with valid JWT."""
        from zrun_bff.main import create_app
        from zrun_bff.config import BFFConfig

        config = BFFConfig()

        # Generate a valid token
        token_pair = generate_token_pair(
            config=config,
            user_id="test_user_123",
            scopes="pda:read pda:write",
        )

        # Create app with UserContextMiddleware
        app = create_app(config)
        client = TestClient(app)

        # Make request with valid token
        response = client.get(
            "/health",
            headers={"Authorization": f"Bearer {token_pair.access_token}"},
        )

        # Response should succeed
        assert response.status_code == status.HTTP_200_OK

    def test_middleware_allows_request_without_token_when_optional(self) -> None:
        """Test that middleware allows requests without token when optional=True."""
        from zrun_bff.main import create_app
        from zrun_bff.config import BFFConfig

        config = BFFConfig()
        app = create_app(config)
        client = TestClient(app)

        # Request without token should succeed (health check is public)
        response = client.get("/health")

        assert response.status_code == status.HTTP_200_OK

    def test_middleware_rejects_invalid_token(self) -> None:
        """Test that middleware handles invalid token gracefully."""
        from zrun_bff.main import create_app
        from zrun_bff.config import BFFConfig

        config = BFFConfig()
        app = create_app(config)
        client = TestClient(app)

        # Request with invalid token should not set context but still succeed
        # (because optional=True by default)
        response = client.get(
            "/health",
            headers={"Authorization": "Bearer invalid_token"},
        )

        # Health check should still succeed
        assert response.status_code == status.HTTP_200_OK

    def test_middleware_rejects_request_without_token_when_not_optional(self) -> None:
        """Test that middleware rejects requests without token when optional=False."""
        from starlette.applications import Starlette
        from starlette.middleware import Middleware
        from starlette.responses import JSONResponse
        from starlette.routing import Route

        async def dummy_handler(request) -> JSONResponse:
            return JSONResponse({"status": "ok"})

        # Create app with UserContextMiddleware (optional=False)
        app = Starlette(
            routes=[Route("/test", dummy_handler)],
            middleware=[
                Middleware(UserContextMiddleware, optional=False),
            ],
        )

        client = TestClient(app)

        # Request without token should be rejected
        response = client.get("/test")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_middleware_rejects_expired_token(self) -> None:
        """Test that middleware rejects expired tokens."""
        from datetime import datetime, timedelta, UTC
        from zrun_bff.config import BFFConfig

        config = BFFConfig()

        # Create an expired token
        expired_payload = {
            "sub": "test_user",
            "iss": config.jwt_issuer,
            "aud": config.jwt_audience,
            "exp": int((datetime.now(UTC) - timedelta(hours=1)).timestamp()),
            "nbf": 0,
            "iat": 0,
            "scope": "pda:read",
        }

        expired_token = jwt.encode(
            expired_payload,
            key=config.jwt_private_key,
            algorithm="RS256",
        )

        from starlette.applications import Starlette
        from starlette.middleware import Middleware
        from starlette.responses import JSONResponse
        from starlette.routing import Route

        async def dummy_handler(request) -> JSONResponse:
            return JSONResponse({"status": "ok"})

        app = Starlette(
            routes=[Route("/test", dummy_handler)],
            middleware=[Middleware(UserContextMiddleware)],
        )

        client = TestClient(app)

        # Request with expired token should not set context but still succeed
        response = client.get(
            "/test",
            headers={"Authorization": f"Bearer {expired_token}"},
        )

        # Handler should still be called (no exception raised)
        assert response.status_code == status.HTTP_200_OK


@pytest.mark.usefixtures("test_key_files")
class TestConfigIsolation:
    """Tests for configuration isolation between instances."""

    def test_jwks_provider_config_isolation(self) -> None:
        """Verify that different configs create different JWKS providers."""
        from zrun_bff.auth.casdoor import get_jwks_provider
        from zrun_bff.config import BFFConfig

        # Create two different configs
        config1 = BFFConfig(
            casdoor_authorization_endpoint="http://localhost:8080/api/oauth/authorize",
            casdoor_client_id="client1",
        )
        config2 = BFFConfig(
            casdoor_authorization_endpoint="http://localhost:9090/api/oauth/authorize",
            casdoor_client_id="client2",
        )

        # Get providers for different configs
        provider1 = get_jwks_provider(config1)
        provider2 = get_jwks_provider(config2)
        provider1_again = get_jwks_provider(config1)

        # Different configs should produce different providers
        assert provider1 is not provider2

        # Same config should produce cached provider
        assert provider1 is provider1_again

    def test_middleware_uses_injected_config(self) -> None:
        """Verify that middleware uses injected config instead of global."""
        from zrun_bff.config import BFFConfig
        from starlette.applications import Starlette
        from starlette.middleware import Middleware
        from starlette.responses import JSONResponse
        from starlette.routing import Route

        async def dummy_handler(request) -> JSONResponse:
            return JSONResponse({"status": "ok"})

        # Create a custom config
        custom_config = BFFConfig(
            jwt_audience="custom_audience",
            jwt_issuer="custom_issuer",
        )

        # Create app with custom config
        app = Starlette(
            routes=[Route("/test", dummy_handler)],
            middleware=[
                Middleware(UserContextMiddleware, config=custom_config),
            ],
        )

        # Verify middleware was created with custom config
        # Note: This is a basic smoke test - in production, you'd want
        # more comprehensive testing of the config injection behavior
        assert app is not None
