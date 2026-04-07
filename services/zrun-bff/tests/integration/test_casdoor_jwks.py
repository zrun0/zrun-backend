"""Integration tests for Casdoor JWKS token verification.

Tests the complete JWKS-based token verification flow including:
- Valid token verification
- Expired token rejection
- Invalid signature rejection
- JWKS key matching
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from jose import jwt

from zrun_bff.auth.casdoor import get_jwks_provider, verify_casdoor_token_async
from zrun_bff.config import BFFConfig, get_config


@pytest.fixture
def test_key_files() -> Generator[str]:
    """Create temporary RSA key pair for testing.

    This fixture sets up test keys and clears the config cache
    to ensure the new key path is loaded.
    """
    # Generate RSA key pair
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend(),
    )

    # Export private key in PEM format
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")

    # Export public key in PEM format
    public_pem = (
        private_key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("utf-8")
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        private_key_path = Path(tmpdir) / "test_private.pem"
        public_key_path = Path(tmpdir) / "test_public.pem"

        private_key_path.write_text(private_pem)
        public_key_path.write_text(public_pem)

        # Set environment variables
        original_private = os.environ.get("JWT_PRIVATE_KEY_PATH")
        original_public = os.environ.get("JWT_PUBLIC_KEY_PATH")

        os.environ["JWT_PRIVATE_KEY_PATH"] = str(private_key_path)
        os.environ["JWT_PUBLIC_KEY_PATH"] = str(public_key_path)

        # Clear config cache to reload keys
        get_config.cache_clear()

        try:
            yield tmpdir
        finally:
            # Restore environment
            if original_private:
                os.environ["JWT_PRIVATE_KEY_PATH"] = original_private
            else:
                os.environ.pop("JWT_PRIVATE_KEY_PATH", None)

            if original_public:
                os.environ["JWT_PUBLIC_KEY_PATH"] = original_public
            else:
                os.environ.pop("JWT_PUBLIC_KEY_PATH", None)

            # Clear cache again to restore original config
            get_config.cache_clear()


def _create_test_token(
    private_key_pem: str,
    sub: str = "test_user",
    exp_seconds: int = 3600,
    kid: str = "test_key",
    audience: str = "test_client",
    issuer: str = "",
) -> str:
    """Create a test JWT token.

    Args:
        private_key_pem: PEM-formatted private key.
        sub: Subject (user ID).
        exp_seconds: Expiration time in seconds.
        kid: Key ID for JWKS.
        audience: Audience claim.
        issuer: Issuer claim (default: "" to match BFF config).

    Returns:
        Encoded JWT token string.
    """
    now = datetime.now(UTC)
    payload = {
        "sub": sub,
        "aud": audience,
        "iss": issuer,
        "iat": now,
        "exp": now + timedelta(seconds=exp_seconds),
        "nbf": now,
    }

    headers = {"kid": kid}

    return jwt.encode(
        claims=payload,
        key=private_key_pem,
        algorithm="RS256",
        headers=headers,
    )


def _create_mock_jwks_response(public_key_pem: str, kid: str = "test_key") -> dict[str, object]:
    """Create a mock JWKS response.

    Args:
        public_key_pem: PEM-formatted public key.
        kid: Key ID for JWKS.

    Returns:
        JWKS dictionary.
    """
    from jose import jwk

    public_key = jwk.construct(public_key_pem, algorithm="RS256")
    public_jwk = public_key.to_dict()

    return {"keys": [{"kid": kid, **public_jwk}]}


class TestValidTokenVerification:
    """Tests for valid token verification."""

    @pytest.mark.asyncio
    async def test_valid_token_verifies_successfully(self, test_key_files: str) -> None:
        """Test that a valid token with correct signature verifies successfully."""
        # Load test keys
        private_key_path = Path(test_key_files) / "test_private.pem"
        public_key_path = Path(test_key_files) / "test_public.pem"

        private_key_pem = private_key_path.read_text()
        public_key_pem = public_key_path.read_text()

        # Create test token
        token = _create_test_token(
            private_key_pem=private_key_pem,
            sub="user123",
            audience="test_client",
        )

        # Create mock JWKS response
        mock_jwks = _create_mock_jwks_response(public_key_pem)

        # Mock HTTP client to return JWKS
        mock_response = MagicMock()
        mock_response.json.return_value = mock_jwks
        mock_response.raise_for_status = MagicMock()

        mock_http_client = MagicMock()
        mock_http_client.get = AsyncMock(return_value=mock_response)

        # Patch the JWKS provider to use our mock HTTP client
        with patch("zrun_core.auth.jwks.httpx.AsyncClient", return_value=mock_http_client):
            # Clear provider cache to force re-creation with mock client
            import zrun_bff.auth.casdoor as casdoor_module

            casdoor_module._jwks_providers.clear()

            # Create config with matching client_id
            config = BFFConfig()
            config.casdoor_client_id = "test_client"

            # Verify token
            payload = await verify_casdoor_token_async(token, config)

            assert payload["sub"] == "user123"
            assert payload["aud"] == "test_client"

    @pytest.mark.asyncio
    async def test_token_with_multiple_scopes_verifies(self, test_key_files: str) -> None:
        """Test that token with multiple scopes verifies successfully."""
        private_key_path = Path(test_key_files) / "test_private.pem"
        public_key_path = Path(test_key_files) / "test_public.pem"

        private_key_pem = private_key_path.read_text()
        public_key_pem = public_key_path.read_text()

        # Create token with scopes
        now = datetime.now(UTC)
        payload = {
            "sub": "user456",
            "aud": "test_client",
            "iss": "",
            "iat": now,
            "exp": now + timedelta(hours=1),
            "nbf": now,
            "scope": "openid profile email",
        }

        token = jwt.encode(
            claims=payload,
            key=private_key_pem,
            algorithm="RS256",
            headers={"kid": "test_key"},
        )

        # Create mock JWKS response
        mock_jwks = _create_mock_jwks_response(public_key_pem)

        mock_response = MagicMock()
        mock_response.json.return_value = mock_jwks
        mock_response.raise_for_status = MagicMock()

        mock_http_client = MagicMock()
        mock_http_client.get = AsyncMock(return_value=mock_response)

        with patch("zrun_core.auth.jwks.httpx.AsyncClient", return_value=mock_http_client):
            import zrun_bff.auth.casdoor as casdoor_module

            casdoor_module._jwks_providers.clear()

            config = BFFConfig()
            config.casdoor_client_id = "test_client"

            result = await verify_casdoor_token_async(token, config)

            assert result["sub"] == "user456"
            assert result["scope"] == "openid profile email"


class TestExpiredToken:
    """Tests for expired token rejection."""

    @pytest.mark.asyncio
    async def test_expired_token_raises_error(self, test_key_files: str) -> None:
        """Test that an expired token is rejected."""
        private_key_path = Path(test_key_files) / "test_private.pem"
        public_key_path = Path(test_key_files) / "test_public.pem"

        private_key_pem = private_key_path.read_text()
        public_key_pem = public_key_path.read_text()

        # Create already-expired token
        now = datetime.now(UTC)
        payload = {
            "sub": "user789",
            "aud": "test_client",
            "iss": "",
            "iat": now - timedelta(hours=2),
            "exp": now - timedelta(hours=1),  # Expired 1 hour ago
            "nbf": now - timedelta(hours=2),
        }

        token = jwt.encode(
            claims=payload,
            key=private_key_pem,
            algorithm="RS256",
            headers={"kid": "test_key"},
        )

        # Create mock JWKS response
        mock_jwks = _create_mock_jwks_response(public_key_pem)

        mock_response = MagicMock()
        mock_response.json.return_value = mock_jwks
        mock_response.raise_for_status = MagicMock()

        mock_http_client = MagicMock()
        mock_http_client.get = AsyncMock(return_value=mock_response)

        with patch("zrun_core.auth.jwks.httpx.AsyncClient", return_value=mock_http_client):
            import zrun_bff.auth.casdoor as casdoor_module

            casdoor_module._jwks_providers.clear()

            config = BFFConfig()
            config.casdoor_client_id = "test_client"

            with pytest.raises(ValueError, match="Token verification failed"):
                await verify_casdoor_token_async(token, config)

    @pytest.mark.asyncio
    async def test_token_not_yet_valid_raises_error(self, test_key_files: str) -> None:
        """Test that token with nbf in the future is rejected."""
        private_key_path = Path(test_key_files) / "test_private.pem"
        public_key_path = Path(test_key_files) / "test_public.pem"

        private_key_pem = private_key_path.read_text()
        public_key_pem = public_key_path.read_text()

        # Create token with nbf in the future
        now = datetime.now(UTC)
        future_time = now + timedelta(hours=1)
        payload = {
            "sub": "user101",
            "aud": "test_client",
            "iss": "",
            "iat": now,
            "exp": future_time + timedelta(hours=1),
            "nbf": future_time,  # Not valid until 1 hour from now
        }

        token = jwt.encode(
            claims=payload,
            key=private_key_pem,
            algorithm="RS256",
            headers={"kid": "test_key"},
        )

        # Create mock JWKS response
        mock_jwks = _create_mock_jwks_response(public_key_pem)

        mock_response = MagicMock()
        mock_response.json.return_value = mock_jwks
        mock_response.raise_for_status = MagicMock()

        mock_http_client = MagicMock()
        mock_http_client.get = AsyncMock(return_value=mock_response)

        with patch("zrun_core.auth.jwks.httpx.AsyncClient", return_value=mock_http_client):
            import zrun_bff.auth.casdoor as casdoor_module

            casdoor_module._jwks_providers.clear()

            config = BFFConfig()
            config.casdoor_client_id = "test_client"

            with pytest.raises(ValueError, match="Token verification failed"):
                await verify_casdoor_token_async(token, config)


class TestInvalidSignature:
    """Tests for invalid signature rejection."""

    @pytest.mark.asyncio
    async def test_token_with_wrong_signature_raises_error(self, test_key_files: str) -> None:
        """Test that token signed with wrong key is rejected."""
        private_key_path = Path(test_key_files) / "test_private.pem"
        public_key_path = Path(test_key_files) / "test_public.pem"

        # Create token with one key
        private_key_pem = private_key_path.read_text()

        token = _create_test_token(
            private_key_pem=private_key_pem,
            sub="user202",
            audience="test_client",
        )

        # Create a different key for JWKS (mismatch)
        wrong_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend(),
        )
        wrong_public_pem = (
            wrong_key.public_key()
            .public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
            .decode("utf-8")
        )

        # Create mock JWKS response with wrong key
        mock_jwks = _create_mock_jwks_response(wrong_public_pem)

        mock_response = MagicMock()
        mock_response.json.return_value = mock_jwks
        mock_response.raise_for_status = MagicMock()

        mock_http_client = MagicMock()
        mock_http_client.get = AsyncMock(return_value=mock_response)

        with patch("zrun_core.auth.jwks.httpx.AsyncClient", return_value=mock_http_client):
            import zrun_bff.auth.casdoor as casdoor_module

            casdoor_module._jwks_providers.clear()

            config = BFFConfig()
            config.casdoor_client_id = "test_client"

            with pytest.raises(ValueError, match="Token verification failed"):
                await verify_casdoor_token_async(token, config)


class TestAudienceValidation:
    """Tests for audience claim validation."""

    @pytest.mark.asyncio
    async def test_token_with_wrong_audience_raises_error(self, test_key_files: str) -> None:
        """Test that token with wrong audience is rejected."""
        private_key_path = Path(test_key_files) / "test_private.pem"
        public_key_path = Path(test_key_files) / "test_public.pem"

        private_key_pem = private_key_path.read_text()
        public_key_pem = public_key_path.read_text()

        # Create token with different audience
        token = _create_test_token(
            private_key_pem=private_key_pem,
            sub="user303",
            audience="wrong_client",  # Wrong audience
        )

        # Create mock JWKS response
        mock_jwks = _create_mock_jwks_response(public_key_pem)

        mock_response = MagicMock()
        mock_response.json.return_value = mock_jwks
        mock_response.raise_for_status = MagicMock()

        mock_http_client = MagicMock()
        mock_http_client.get = AsyncMock(return_value=mock_response)

        with patch("zrun_core.auth.jwks.httpx.AsyncClient", return_value=mock_http_client):
            import zrun_bff.auth.casdoor as casdoor_module

            casdoor_module._jwks_providers.clear()

            config = BFFConfig()
            config.casdoor_client_id = "test_client"  # Different from token audience

            with pytest.raises(ValueError, match="Token verification failed"):
                await verify_casdoor_token_async(token, config)


class TestJWKSProviderCaching:
    """Tests for JWKS provider caching behavior."""

    def test_get_jwks_provider_returns_singleton(self) -> None:
        """Test that get_jwks_provider returns cached instance."""
        provider1 = get_jwks_provider()
        provider2 = get_jwks_provider()

        # Should return the same instance
        assert provider1 is provider2

    @pytest.mark.asyncio
    async def test_jwks_provider_cache_isolation(self, test_key_files: str) -> None:
        """Test that JWKS provider cache works correctly with config changes."""
        # Get provider with test config
        provider = get_jwks_provider()

        # Verify it's the correct type
        from zrun_core.auth import JWKSProvider

        assert isinstance(provider, JWKSProvider)
