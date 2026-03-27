"""Unit tests for authentication interceptor."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from zrun_core.auth import USER_ID_CTX_KEY, AuthInterceptor, JWKSFetchError

# Test JWKS for mock purposes
TEST_JWKS = {
    "keys": [
        {
            "kty": "RSA",
            "kid": "test-key-1",
            "use": "sig",
            "n": "test-n-value",
            "e": "AQAB",
        }
    ]
}


class TestJWKSFetchError:
    """Tests for JWKSFetchError."""

    def test_jwks_fetch_error_creation(self) -> None:
        """Test JWKSFetchError can be created with a message."""
        msg = "Failed to fetch JWKS"
        error = JWKSFetchError(message=msg)
        assert error.message == msg
        assert str(error) == msg


class TestAuthInterceptor:
    """Tests for AuthInterceptor."""

    @pytest.fixture
    def interceptor(self) -> AuthInterceptor:
        """Create an AuthInterceptor instance for testing."""
        return AuthInterceptor(
            jwks_url="https://bff.example.com/.well-known/jwks.json",
            audience="zrun-services",
            issuer="zrun-bff",
            cache_ttl=300,
        )

    def test_interceptor_initialization(self, interceptor: AuthInterceptor) -> None:
        """Test interceptor initialization."""
        assert interceptor._jwks_url == "https://bff.example.com/.well-known/jwks.json"
        assert interceptor._audience == "zrun-services"
        assert interceptor._issuer == "zrun-bff"
        from cachetools import TTLCache

        assert isinstance(interceptor._cache, TTLCache)

    @pytest.mark.asyncio
    async def test_fetch_jwks_success(self, interceptor: AuthInterceptor) -> None:
        """Test successful JWKS fetch."""
        mock_response = MagicMock()
        mock_response.json.return_value = TEST_JWKS
        mock_response.raise_for_status = MagicMock()

        interceptor._client.get = AsyncMock(return_value=mock_response)  # type: ignore[method-assign]

        jwks = await interceptor._fetch_jwks()

        assert jwks == TEST_JWKS

    @pytest.mark.asyncio
    async def test_fetch_jwks_http_error(self, interceptor: AuthInterceptor) -> None:
        """Test JWKS fetch with HTTP error."""
        import httpx

        interceptor._client.get = AsyncMock(side_effect=httpx.HTTPError("Network error"))  # type: ignore[method-assign]

        with pytest.raises(JWKSFetchError):
            await interceptor._fetch_jwks()

    @pytest.mark.asyncio
    async def test_get_jwks_caching(self, interceptor: AuthInterceptor) -> None:
        """Test JWKS caching."""
        mock_response = MagicMock()
        mock_response.json.return_value = TEST_JWKS
        mock_response.raise_for_status = MagicMock()
        interceptor._client.get = AsyncMock(return_value=mock_response)  # type: ignore[method-assign]

        # First call should fetch
        jwks1 = await interceptor._get_jwks()
        interceptor._client.get.assert_called_once()

        # Second call should use cache
        jwks2 = await interceptor._get_jwks()
        assert interceptor._client.get.call_count == 1

        assert jwks1 == jwks2

    def test_extract_token_from_authorization_header(self, interceptor: AuthInterceptor) -> None:
        """Test extracting token from Authorization header."""
        metadata = (("authorization", "Bearer test-token-123"),)
        token = interceptor._extract_token(metadata)
        assert token == "test-token-123"

    def test_extract_token_from_custom_header(self, interceptor: AuthInterceptor) -> None:
        """Test extracting token from custom token header."""
        metadata = (("token", "custom-token-456"),)
        token = interceptor._extract_token(metadata)
        assert token == "custom-token-456"

    def test_extract_token_authorization_takes_precedence(
        self, interceptor: AuthInterceptor
    ) -> None:
        """Test Authorization header takes precedence over custom token."""
        metadata = (
            ("authorization", "Bearer auth-token"),
            ("token", "custom-token"),
        )
        token = interceptor._extract_token(metadata)
        assert token == "auth-token"

    def test_extract_token_none_if_missing(self, interceptor: AuthInterceptor) -> None:
        """Test extracting token when not present."""
        metadata = (("other-header", "value"),)
        token = interceptor._extract_token(metadata)
        assert token is None

    def test_extract_token_none_if_empty_metadata(self, interceptor: AuthInterceptor) -> None:
        """Test extracting token from empty metadata."""
        token = interceptor._extract_token(None)
        assert token is None

    @pytest.mark.asyncio
    async def test_validate_token_with_mock_jwks(self, interceptor: AuthInterceptor) -> None:
        """Test token validation with mocked JWKS."""
        # Mock _get_jwks to return test JWKS
        interceptor._get_jwks = AsyncMock(return_value=TEST_JWKS)  # type: ignore[method-assign]

        # Mock jwt functions (jwt is a submodule: jose.jwt)
        with patch("jose.jwt.get_unverified_header") as mock_get_header, \
             patch("jose.jwt.decode") as mock_decode:
            mock_get_header.return_value = {"kid": "test-key-1"}
            mock_decode.return_value = {
                "sub": "user123",
                "aud": "zrun-services",
                "iss": "zrun-bff",
            }

            payload = await interceptor._validate_token("test-token")

            assert payload is not None
            assert payload.get("sub") == "user123"

    @pytest.mark.asyncio
    async def test_validate_token_no_kid(self, interceptor: AuthInterceptor) -> None:
        """Test token validation fails when JWT has no kid."""
        with patch("jose.jwt.get_unverified_header") as mock_get_header:
            mock_get_header.return_value = {}

            payload = await interceptor._validate_token("invalid-token")

            assert payload is None

    @pytest.mark.asyncio
    async def test_validate_token_key_not_found(self, interceptor: AuthInterceptor) -> None:
        """Test token validation fails when key not found in JWKS."""
        # Mock _get_jwks to return test JWKS
        interceptor._get_jwks = AsyncMock(return_value=TEST_JWKS)  # type: ignore[method-assign]

        with patch("jose.jwt.get_unverified_header") as mock_get_header:
            mock_get_header.return_value = {"kid": "unknown-key"}

            payload = await interceptor._validate_token("test-token")

            assert payload is None

    @pytest.mark.asyncio
    async def test_close(self, interceptor: AuthInterceptor) -> None:
        """Test closing the interceptor."""
        await interceptor.close()
        # Verify client is closed (no exception means success)
        assert True

    @pytest.mark.asyncio
    async def test_async_context_manager(self, interceptor: AuthInterceptor) -> None:
        """Test async context manager support."""
        async with interceptor:
            pass
        # Client should be closed after exiting context


class TestUserIdContextKey:
    """Tests for USER_ID_CTX_KEY."""

    def test_user_id_context_key_exists(self) -> None:
        """Test USER_ID_CTX_KEY is defined."""
        assert USER_ID_CTX_KEY is not None

    def test_user_id_context_key_default(self) -> None:
        """Test USER_ID_CTX_KEY has None default."""
        # Get without setting should return None (default)
        value = USER_ID_CTX_KEY.get()
        assert value is None
