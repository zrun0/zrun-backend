"""End-to-end integration tests for OAuth flow.

These tests cover the core OAuth2 authentication flows including:
- State parameter generation and validation
- Token generation and refresh
- Session management
- Error scenarios
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Generator
from pathlib import Path
from unittest.mock import patch

import pytest
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from fastapi import status
from fastapi.testclient import TestClient
from jose import jwt


@pytest.mark.usefixtures("test_key_files")
class TestE2EOAuthStateFlow:
    """End-to-end tests for OAuth state parameter management."""

    @pytest.fixture
    def test_key_files(self) -> Generator[str]:
        """Create temporary key files for testing.

        Yields:
            Path to temporary directory containing the key files.
        """
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

    def test_login_redirect_generates_secure_state(
        self,
    ) -> None:
        """Test that login redirect generates a cryptographically secure state."""
        from zrun_bff.main import create_app
        from zrun_bff.config import BFFConfig

        config = BFFConfig()
        app = create_app(config)
        client = TestClient(app)

        response = client.get("/auth/login", follow_redirects=False)

        assert response.status_code == status.HTTP_302_FOUND
        location = response.headers.get("location", "")

        # Verify state parameter exists
        assert "state=" in location

        # Extract and verify state length
        from urllib.parse import parse_qs, urlparse

        parsed = urlparse(location)
        params = parse_qs(parsed.query)
        state = params.get("state", [None])[0]

        assert state is not None
        # State should be at least 32 characters (token_urlsafe(32) = 43 chars)
        assert len(state) >= 32

    def test_oauth_state_mismatch_is_blocked(
        self,
    ) -> None:
        """Test that callback without proper session state is blocked.

        This verifies that the OAuth callback requires a valid session
        with a stored state parameter, preventing CSRF attacks.

        """
        from zrun_bff.main import create_app
        from zrun_bff.config import BFFConfig

        config = BFFConfig()
        app = create_app(config)
        client = TestClient(app)

        # Direct callback without login (no session state)
        # This simulates a CSRF attack where the attacker tries to bypass
        # the state parameter validation
        callback_response = client.get(
            "/auth/callback?code=auth_code_123&state=attacker_state",
            follow_redirects=False,
        )

        # Should be rejected - either 400 for missing state or invalid state
        assert callback_response.status_code == status.HTTP_400_BAD_REQUEST

    def test_expired_session_is_blocked(
        self,
    ) -> None:
        """Test that expired session (missing state) is blocked."""
        from zrun_bff.main import create_app
        from zrun_bff.config import BFFConfig

        config = BFFConfig()
        app = create_app(config)
        client = TestClient(app)

        # Direct callback without login (no session state)
        callback_response = client.get(
            "/auth/callback?code=auth_code_123",
            follow_redirects=False,
        )

        assert callback_response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Missing state parameter" in callback_response.json()["detail"]

    def test_session_state_prevents_replay_attack(
        self,
    ) -> None:
        """Test that state can only be used once (replay protection)."""
        from zrun_bff.main import create_app
        from zrun_bff.config import BFFConfig

        config = BFFConfig()
        app = create_app(config)
        client = TestClient(app)

        # Login
        login_response = client.get("/auth/login", follow_redirects=False)
        location = login_response.headers.get("location", "")

        from urllib.parse import parse_qs, urlparse

        parsed = urlparse(location)
        params = parse_qs(parsed.query)
        state = params.get("state", [None])[0]

        # First callback with proper mocking
        with (
            patch("httpx.AsyncClient"),
            patch(
                "zrun_bff.auth.router.verify_casdoor_token_async", return_value={"sub": "user123"}
            ),
        ):
            client.get(
                f"/auth/callback?code=auth_code_123&state={state}",
                follow_redirects=False,
            )

        # Second callback with same state should fail (state already consumed)
        callback_response2 = client.get(
            f"/auth/callback?code=auth_code_456&state={state}",
            follow_redirects=False,
        )

        assert callback_response2.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.usefixtures("test_key_files")
class TestE2ETokenManagement:
    """End-to-end tests for token generation and refresh."""

    @pytest.fixture
    def test_key_files(self) -> Generator[str]:
        """Create temporary key files for testing.

        Yields:
            Path to temporary directory containing the key files.
        """
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

    def test_token_pair_contains_valid_claims(
        self,
    ) -> None:
        """Test that generated token pair contains valid claims."""
        from zrun_bff.auth.tokens import generate_token_pair
        from zrun_bff.config import BFFConfig

        config = BFFConfig()

        token_pair = generate_token_pair(
            config=config,
            user_id="test_user",
            scopes="pda:read pda:write",
        )

        # Verify access token
        access_payload = jwt.decode(
            token_pair.access_token,
            key=config.jwt_private_key,
            algorithms=["RS256"],
            audience=config.jwt_audience,
        )

        assert access_payload["sub"] == "test_user"
        assert access_payload["iss"] == config.jwt_issuer
        assert access_payload["aud"] == config.jwt_audience
        assert access_payload["token_type"] == "access"
        assert "pda:read" in access_payload["scope"]

        # Verify refresh token
        refresh_payload = jwt.decode(
            token_pair.refresh_token,
            key=config.jwt_private_key,
            algorithms=["RS256"],
            audience=config.jwt_audience,
        )

        assert refresh_payload["sub"] == "test_user"
        assert refresh_payload["token_type"] == "refresh"

        # Verify token pair metadata
        assert token_pair.expires_in == config.jwt_expiration_seconds
        assert token_pair.token_type == "Bearer"

    def test_token_refresh_rotates_tokens(
        self,
    ) -> None:
        """Test that token refresh generates new tokens (token rotation)."""
        from zrun_bff.auth.tokens import generate_token_pair, refresh_access_token
        from zrun_bff.config import BFFConfig

        config = BFFConfig()

        # Generate initial token pair
        initial_pair = generate_token_pair(
            config=config,
            user_id="test_user",
            scopes="pda:read pda:write",
        )

        # Add delay to ensure different timestamp
        import time

        time.sleep(0.01)

        # Refresh the token
        new_pair = refresh_access_token(
            config=config,
            refresh_token=initial_pair.refresh_token,
        )

        # Verify new access token (with different iat)
        old_payload = jwt.decode(
            initial_pair.access_token,
            key=config.jwt_private_key,
            algorithms=["RS256"],
            options={"verify_aud": False, "verify_exp": False},
        )

        new_payload = jwt.decode(
            new_pair.access_token,
            key=config.jwt_private_key,
            algorithms=["RS256"],
            options={"verify_aud": False, "verify_exp": False},
        )

        assert old_payload["sub"] == new_payload["sub"]
        # New token should have later or equal issued-at time
        assert old_payload["iat"] <= new_payload["iat"]

    def test_refresh_token_requires_valid_type(
        self,
    ) -> None:
        """Test that refresh token must have correct token type."""
        from zrun_bff.auth.tokens import generate_token_pair, refresh_access_token
        from zrun_bff.config import BFFConfig

        config = BFFConfig()

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

    def test_expired_refresh_token_is_rejected(
        self,
    ) -> None:
        """Test that expired refresh token is rejected."""
        from datetime import datetime, timedelta, UTC
        from jose import jwt as jose_jwt
        from zrun_bff.auth.tokens import refresh_access_token
        from zrun_bff.config import BFFConfig

        config = BFFConfig()

        # Create an expired refresh token
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

        expired_token = jose_jwt.encode(
            expired_payload,
            key=config.jwt_private_key,
            algorithm="RS256",
        )

        # Verify it's rejected
        with pytest.raises(ValueError, match="expired"):
            refresh_access_token(
                config=config,
                refresh_token=expired_token,
            )


@pytest.mark.usefixtures("test_key_files")
class TestE2EAccessTokenValidation:
    """End-to-end tests for access token validation."""

    @pytest.fixture
    def test_key_files(self) -> Generator[str]:
        """Create temporary key files for testing.

        Yields:
            Path to temporary directory containing the key files.
        """
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

    def test_valid_access_token_is_accepted(
        self,
    ) -> None:
        """Test that valid access token is accepted."""
        from zrun_bff.auth.tokens import generate_token_pair, verify_access_token
        from zrun_bff.config import BFFConfig

        config = BFFConfig()

        token_pair = generate_token_pair(
            config=config,
            user_id="test_user_123",
            scopes="pda:read pda:write",
        )

        claims = verify_access_token(config, token_pair.access_token)

        assert claims.sub == "test_user_123"
        assert claims.token_type == "access"
        assert "pda:read" in claims.scope
        assert "pda:write" in claims.scope

    def test_expired_access_token_is_rejected(
        self,
    ) -> None:
        """Test that expired access token is rejected."""
        from datetime import datetime, timedelta, UTC
        from jose import jwt as jose_jwt
        from zrun_bff.auth.tokens import verify_access_token
        from zrun_bff.config import BFFConfig

        config = BFFConfig()

        # Create an expired access token
        expired_payload = {
            "sub": "test_user",
            "iss": config.jwt_issuer,
            "aud": config.jwt_audience,
            "exp": int((datetime.now(UTC) - timedelta(hours=1)).timestamp()),
            "nbf": 0,
            "iat": 0,
            "scope": "pda:read",
            "token_type": "access",
        }

        expired_token = jose_jwt.encode(
            expired_payload,
            key=config.jwt_private_key,
            algorithm="RS256",
        )

        with pytest.raises(ValueError, match="expired"):
            verify_access_token(config, expired_token)

    def test_refresh_token_as_access_token_is_rejected(
        self,
    ) -> None:
        """Test that using refresh token as access token is rejected."""
        from zrun_bff.auth.tokens import generate_token_pair, verify_access_token
        from zrun_bff.config import BFFConfig

        config = BFFConfig()

        token_pair = generate_token_pair(
            config=config,
            user_id="test_user",
        )

        with pytest.raises(ValueError, match="Invalid token type"):
            verify_access_token(config, token_pair.refresh_token)
