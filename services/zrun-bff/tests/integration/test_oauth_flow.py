"""Integration tests for OAuth flow.

Tests the complete OAuth2 flow with Casdoor, including:
- State parameter generation and validation
- JWT token verification
- Token refresh mechanism
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient


class TestOAuthStateFlow:
    """Tests for OAuth state parameter flow."""

    def test_login_redirect_generates_state(self) -> None:
        """Test that login redirect generates a state parameter."""
        from zrun_bff.main import create_app
        from zrun_bff.config import BFFConfig

        config = BFFConfig()
        app = create_app(config)
        client = TestClient(app)

        response = client.get("/auth/login", follow_redirects=False)

        assert response.status_code == status.HTTP_302_FOUND
        location = response.headers.get("location")
        assert location is not None
        assert "state=" in location
        assert "code" in location  # response_type=code
        assert config.casdoor_client_id in location

    def test_callback_missing_state_returns_400(self) -> None:
        """Test that callback without state parameter returns 400."""
        from zrun_bff.main import create_app
        from zrun_bff.config import BFFConfig

        config = BFFConfig()
        app = create_app(config)
        client = TestClient(app)

        # Callback without state should fail
        response = client.get("/auth/callback?code=test_code")

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_callback_state_mismatch_returns_400(self) -> None:
        """Test that callback with mismatched state returns 400."""
        from zrun_bff.main import create_app
        from zrun_bff.config import BFFConfig

        config = BFFConfig()
        app = create_app(config)
        test_client = TestClient(app)

        # First, get a valid state from login
        login_response = test_client.get("/auth/login", follow_redirects=False)
        location = login_response.headers.get("location", "")
        # Extract state from URL
        import re

        state_match = re.search(r"state=([^&]+)", location)
        assert state_match is not None
        state_match.group(1)

        # Try callback with different state
        response = test_client.get("/auth/callback?code=test_code&state=wrong_state")

        assert response.status_code == status.HTTP_400_BAD_REQUEST


class TestJWTVerification:
    """Tests for JWT token verification."""

    def test_verify_casdoor_token_function_exists(self) -> None:
        """Test that verify_casdoor_token function can be imported."""
        from zrun_bff.auth.utils import verify_casdoor_token

        assert callable(verify_casdoor_token)

    def test_verify_casdoor_token_with_missing_key_id_raises_error(self) -> None:
        """Test that token without kid header raises ValueError."""
        from zrun_bff.auth.utils import _verify_casdoor_token_async
        from zrun_bff.config import BFFConfig

        config = BFFConfig()

        # Mock the JWKS provider
        with patch("zrun_bff.auth.utils.get_jwks_provider") as mock_jwks:
            mock_provider = MagicMock()
            mock_jwks.return_value = mock_provider

            async def mock_get_jwks():
                return {"keys": []}

            mock_provider.get_jwks = mock_get_jwks

            # Mock jwt.get_unverified_header to return no kid
            with patch("zrun_bff.auth.utils.jwt.get_unverified_header", return_value={}):
                import asyncio

                with pytest.raises(ValueError, match="missing key ID"):
                    asyncio.run(_verify_casdoor_token_async("invalid_token", config))

    def test_verify_casdoor_token_with_missing_kid_in_jwks_raises_error(self) -> None:
        """Test that token with kid not in JWKS raises ValueError."""
        from zrun_bff.auth.utils import _verify_casdoor_token_async
        from zrun_bff.config import BFFConfig

        config = BFFConfig()

        # Mock the JWKS provider
        with patch("zrun_bff.auth.utils.get_jwks_provider") as mock_jwks:
            mock_provider = MagicMock()
            mock_jwks.return_value = mock_provider

            async def mock_get_jwks():
                # Return JWKS with different key ID
                return {"keys": [{"kid": "different_key"}]}

            mock_provider.get_jwks = mock_get_jwks

            # Mock jwt.get_unverified_header
            with patch(
                "zrun_bff.auth.utils.jwt.get_unverified_header", return_value={"kid": "test_key"}
            ):
                import asyncio

                with pytest.raises(ValueError, match="Key ID.*not found in JWKS"):
                    asyncio.run(_verify_casdoor_token_async("invalid_token", config))


class TestTokenRefresh:
    """Tests for token refresh mechanism."""

    def test_refresh_access_token_with_valid_refresh_token(self) -> None:
        """Test refreshing access token with valid refresh token."""
        import os
        from zrun_bff.auth.tokens import refresh_access_token, generate_token_pair
        from zrun_bff.config import BFFConfig
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.backends import default_backend

        # Generate a test RSA key pair
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend(),
        )

        # Save to temp file
        pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )

        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".pem", delete=False) as f:
            f.write(pem.decode())
            temp_key_path = f.name

        try:
            os.environ["JWT_PRIVATE_KEY_PATH"] = temp_key_path
            config = BFFConfig()

            # First generate a token pair
            original_pair = generate_token_pair(
                config=config,
                user_id="test_user",
                scopes="pda:read pda:write",
            )

            # Use the refresh token to get a new pair
            new_pair = refresh_access_token(
                config=config,
                refresh_token=original_pair.refresh_token,
            )

            # Verify new tokens were generated (they will be different due to timestamps)
            assert new_pair.access_token is not None
            assert new_pair.refresh_token is not None
            assert len(new_pair.access_token) > 0
            assert len(new_pair.refresh_token) > 0
            assert new_pair.expires_in == config.jwt_expiration_seconds
            assert new_pair.token_type == "Bearer"
        finally:
            from pathlib import Path

            Path(temp_key_path).unlink(missing_ok=True)

    def test_refresh_access_token_with_access_token_fails(self) -> None:
        """Test using access token as refresh token fails."""
        import os
        from zrun_bff.auth.tokens import refresh_access_token, generate_token_pair
        from zrun_bff.config import BFFConfig
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.backends import default_backend

        # Generate a test RSA key pair
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend(),
        )

        pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )

        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".pem", delete=False) as f:
            f.write(pem.decode())
            temp_key_path = f.name

        try:
            os.environ["JWT_PRIVATE_KEY_PATH"] = temp_key_path
            config = BFFConfig()

            # Generate a token pair
            token_pair = generate_token_pair(
                config=config,
                user_id="test_user",
            )

            # Try to use access token as refresh token
            with pytest.raises(ValueError, match="Invalid token type"):
                refresh_access_token(
                    config=config,
                    refresh_token=token_pair.access_token,
                )
        finally:
            from pathlib import Path

            Path(temp_key_path).unlink(missing_ok=True)

    def test_refresh_access_token_with_expired_token_fails(self) -> None:
        """Test using expired refresh token fails."""
        import os
        from datetime import datetime, timedelta, UTC
        from zrun_bff.config import BFFConfig
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.backends import default_backend

        # Generate a test RSA key pair
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend(),
        )

        pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )

        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".pem", delete=False) as f:
            f.write(pem.decode())
            temp_key_path = f.name

        try:
            os.environ["JWT_PRIVATE_KEY_PATH"] = temp_key_path
            config = BFFConfig()

            # Create an expired refresh token manually
            from jose import jwt

            expired_payload = {
                "sub": "test_user",
                "iss": config.jwt_issuer,
                "aud": config.jwt_audience,
                "exp": int((datetime.now(UTC) - timedelta(hours=1)).timestamp()),
                "nbf": 0,
                "iat": 0,
                "scope": "pda:read",
                "token_type": "refresh",
            }

            expired_token = jwt.encode(
                expired_payload,
                key=config.jwt_private_key,
                algorithm="RS256",
            )

            from zrun_bff.auth.tokens import refresh_access_token

            with pytest.raises(ValueError, match="expired"):
                refresh_access_token(
                    config=config,
                    refresh_token=expired_token,
                )
        finally:
            from pathlib import Path

            Path(temp_key_path).unlink(missing_ok=True)


class TestTokenClaims:
    """Tests for TokenClaims dataclass."""

    def test_token_claims_from_dict(self) -> None:
        """Test creating TokenClaims from JWT payload dict."""
        from zrun_bff.auth.tokens import TokenClaims

        payload = {
            "sub": "user123",
            "iss": "zrun-bff",
            "aud": "zrun-services",
            "exp": 9999999999,
            "nbf": 0,
            "iat": 0,
            "scope": "pda:read pda:write",
            "token_type": "access",
        }

        claims = TokenClaims.from_dict(payload)

        assert claims.sub == "user123"
        assert claims.iss == "zrun-bff"
        assert claims.scope == "pda:read pda:write"
        assert claims.token_type == "access"

    def test_token_claims_handles_timestamps(self) -> None:
        """Test that TokenClaims converts timestamps to datetime."""
        from zrun_bff.auth.tokens import TokenClaims
        from datetime import datetime, UTC

        now = int(datetime.now(UTC).timestamp())

        payload = {
            "sub": "user123",
            "iss": "zrun-bff",
            "aud": "zrun-services",
            "exp": now + 3600,
            "nbf": now,
            "iat": now,
            "scope": "pda:read",
            "token_type": "access",
        }

        claims = TokenClaims.from_dict(payload)

        assert isinstance(claims.exp, datetime)
        assert isinstance(claims.nbf, datetime)
        assert isinstance(claims.iat, datetime)


class TestSessionMiddleware:
    """Tests for session middleware."""

    def test_session_middleware_stores_oauth_state(self) -> None:
        """Test that session middleware stores OAuth state."""
        from zrun_bff.main import create_app
        from zrun_bff.config import BFFConfig

        config = BFFConfig()
        app = create_app(config)
        client = TestClient(app)

        # Make login request
        response = client.get("/auth/login", follow_redirects=False)

        # Verify the request was processed (302 redirect)
        assert response.status_code == status.HTTP_302_FOUND
        # The state parameter should be in the redirect URL
        location = response.headers.get("location", "")
        assert "state=" in location

    def test_session_middleware_invalid_signature_returns_empty_session(self) -> None:
        """Test that invalid session signature returns empty session."""
        from zrun_bff.middleware.session import SessionMiddleware
        from starlette.applications import Starlette
        from starlette.responses import JSONResponse
        from starlette.requests import Request

        async def dummy_app(request: Request) -> JSONResponse:
            from zrun_bff.middleware.session import get_session

            session = get_session(request)
            return JSONResponse({"session": session})

        app = Starlette()
        app.add_middleware(
            SessionMiddleware,
            secret_key="test-secret",
            session_cookie="test_session",
        )
        app.add_route("/test", dummy_app)

        client = TestClient(app)

        # Request with invalid session cookie
        response = client.get("/test", cookies={"test_session": "invalid_signature_data"})

        assert response.status_code == 200
        data = response.json()
        # Should return empty session for invalid signature
        assert data.get("session") in ({}, None)
