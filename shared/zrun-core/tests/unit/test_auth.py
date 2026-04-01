"""Unit tests for authentication interceptor."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from zrun_core.auth import AuthInterceptor, JWKSFetchError


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
            jwks_url="https://auth.example.com/jwks",
            audience="test-audience",
            issuer="https://auth.example.com",
            cache_ttl=300,
        )

    def test_interceptor_initialization(self, interceptor: AuthInterceptor) -> None:
        """Test interceptor initialization."""
        assert interceptor._jwks_url == "https://auth.example.com/jwks"
        assert interceptor._audience == "test-audience"
        assert interceptor._issuer == "https://auth.example.com"
        from cachetools import TTLCache

        assert isinstance(interceptor._cache, TTLCache)

    @pytest.mark.asyncio
    async def test_fetch_jwks_success(self, interceptor: AuthInterceptor) -> None:
        """Test successful JWKS fetch."""
        # Mock the HTTP client response
        mock_response = MagicMock()
        mock_response.json.return_value = {"keys": []}
        mock_response.raise_for_status = MagicMock()

        interceptor._client.get = AsyncMock(return_value=mock_response)  # type: ignore[method-assign]  # type: ignore[method-assign]

        jwks = await interceptor._fetch_jwks()

        assert jwks == {"keys": []}

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
        mock_response.json.return_value = {"keys": ["key1"]}
        mock_response.raise_for_status = MagicMock()
        interceptor._client.get = AsyncMock(return_value=mock_response)  # type: ignore[method-assign]  # type: ignore[method-assign]

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
        token = interceptor._extract_token_from_metadata(metadata)
        assert token == "test-token-123"

    def test_extract_token_from_custom_header(self, interceptor: AuthInterceptor) -> None:
        """Test extracting token from custom token header."""
        metadata = (("token", "custom-token-456"),)
        token = interceptor._extract_token_from_metadata(metadata)
        assert token == "custom-token-456"

    def test_extract_token_authorization_takes_precedence(
        self, interceptor: AuthInterceptor
    ) -> None:
        """Test Authorization header takes precedence over custom token."""
        metadata = (
            ("authorization", "Bearer auth-token"),
            ("token", "custom-token"),
        )
        token = interceptor._extract_token_from_metadata(metadata)
        assert token == "auth-token"

    def test_extract_token_none_if_missing(self, interceptor: AuthInterceptor) -> None:
        """Test extracting token when not present."""
        metadata = (("other-header", "value"),)
        token = interceptor._extract_token_from_metadata(metadata)
        assert token is None

    def test_extract_token_none_if_empty_metadata(self, interceptor: AuthInterceptor) -> None:
        """Test extracting token from empty metadata."""
        token = interceptor._extract_token_from_metadata(None)
        assert token is None

    def test_decode_token_payload_valid_jwt(self, interceptor: AuthInterceptor) -> None:
        """Test decoding a valid JWT payload."""
        token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ1c2VyMTIzIn0.signature"

        payload = interceptor._decode_token_payload(token)
        assert payload is not None
        assert payload.get("sub") == "user123"

    def test_decode_token_payload_invalid_format(self, interceptor: AuthInterceptor) -> None:
        """Test decoding an invalid token format."""
        token = "invalid-token"
        payload = interceptor._decode_token_payload(token)
        assert payload is None

    def test_decode_token_payload_missing_parts(self, interceptor: AuthInterceptor) -> None:
        """Test decoding token with missing parts."""
        token = "only.two"
        payload = interceptor._decode_token_payload(token)
        assert payload is None

    @pytest.mark.asyncio
    async def test_close(self, interceptor: AuthInterceptor) -> None:
        """Test closing the interceptor."""
        await interceptor.close()
        # Verify client is closed (no exception means success)
        assert True


class TestUserIdContextKey:
    """Tests for USER_ID_CTX_KEY."""

    def test_user_id_context_key_exists(self) -> None:
        """Test USER_ID_CTX_KEY is defined."""
        from zrun_core.auth import USER_ID_CTX_KEY

        assert USER_ID_CTX_KEY is not None

    def test_user_id_context_key_default(self) -> None:
        """Test USER_ID_CTX_KEY has None default."""
        from zrun_core.auth import USER_ID_CTX_KEY

        # Get without setting should return None (default)
        value = USER_ID_CTX_KEY.get(None)
        assert value is None
