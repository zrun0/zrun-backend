"""Unit tests for authentication interceptor."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from zrun_core.auth import (
    JWKSProvider,
    JWKSProviderConfig,
    JWKSProviderError,
    JWTVerificationConfig,
    JWTVerificationError,
    USER_ID_CTX_KEY,
    AuthInterceptor,
    verify_jwt_with_jwks,
)

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


class TestJWKSProviderError:
    """Tests for JWKSProviderError."""

    def test_jwks_provider_error_creation(self) -> None:
        """Test JWKSProviderError can be created with a message."""
        msg = "Failed to fetch JWKS"
        error = JWKSProviderError(message=msg)
        assert error.message == msg
        assert str(error) == msg
        assert error.code == "JWKS_PROVIDER_ERROR"


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
        assert interceptor._jwks_provider is not None
        assert interceptor._jwt_config.audience == "zrun-services"
        assert interceptor._jwt_config.issuer == "zrun-bff"

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
    async def test_close(self, interceptor: AuthInterceptor) -> None:
        """Test closing the interceptor."""
        await interceptor.close()
        # Verify provider is closed (no exception means success)
        assert True

    @pytest.mark.asyncio
    async def test_async_context_manager(self, interceptor: AuthInterceptor) -> None:
        """Test async context manager support."""
        async with interceptor:
            pass
        # Provider should be closed after exiting context


class TestJWKSProvider:
    """Tests for JWKSProvider."""

    @pytest.fixture
    def jwks_config(self) -> JWKSProviderConfig:
        """Create JWKS provider config for testing."""
        return JWKSProviderConfig(
            jwks_url="https://example.com/.well-known/jwks.json",
            cache_ttl_seconds=300,
            timeout_seconds=10,
        )

    @pytest.fixture
    def provider(self, jwks_config: JWKSProviderConfig) -> JWKSProvider:
        """Create JWKS provider for testing."""
        return JWKSProvider(config=jwks_config)

    def test_jwks_provider_initialization(self, provider: JWKSProvider) -> None:
        """Test provider initialization."""
        assert provider._config.jwks_url == "https://example.com/.well-known/jwks.json"
        assert provider._config.cache_ttl_seconds == 300

    @pytest.mark.asyncio
    async def test_get_jwks_success(self, provider: JWKSProvider) -> None:
        """Test successful JWKS fetch."""
        mock_response = MagicMock()
        mock_response.json.return_value = TEST_JWKS
        mock_response.raise_for_status = MagicMock()

        provider._http_client.get = AsyncMock(return_value=mock_response)  # type: ignore[method-assign]

        jwks = await provider.get_jwks()

        assert jwks == TEST_JWKS
        assert "keys" in jwks

    @pytest.mark.asyncio
    async def test_get_jwks_caching(self, provider: JWKSProvider) -> None:
        """Test JWKS caching."""
        mock_response = MagicMock()
        mock_response.json.return_value = TEST_JWKS
        mock_response.raise_for_status = MagicMock()
        provider._http_client.get = AsyncMock(return_value=mock_response)  # type: ignore[method-assign]

        # First call should fetch
        jwks1 = await provider.get_jwks()
        provider._http_client.get.assert_called_once()

        # Second call should use cache
        jwks2 = await provider.get_jwks()
        assert provider._http_client.get.call_count == 1

        assert jwks1 == jwks2

    @pytest.mark.asyncio
    async def test_get_jwks_http_error(self, provider: JWKSProvider) -> None:
        """Test JWKS fetch with HTTP error."""
        import httpx

        provider._http_client.get = AsyncMock(
            side_effect=httpx.HTTPStatusError(  # type: ignore[method-assign]
                "Not Found",
                request=MagicMock(),
                response=MagicMock(status_code=404),
            )
        )

        with pytest.raises(JWKSProviderError):
            await provider.get_jwks()

    @pytest.mark.asyncio
    async def test_get_jwks_invalid_response(self, provider: JWKSProvider) -> None:
        """Test JWKS fetch with invalid response."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"invalid": "response"}
        mock_response.raise_for_status = MagicMock()
        provider._http_client.get = AsyncMock(return_value=mock_response)  # type: ignore[method-assign]

        with pytest.raises(JWKSProviderError):
            await provider.get_jwks()

    @pytest.mark.asyncio
    async def test_close(self, provider: JWKSProvider) -> None:
        """Test closing the provider."""
        await provider.close()
        # Verify client is closed (no exception means success)
        assert True

    @pytest.mark.asyncio
    async def test_async_context_manager(self, jwks_config: JWKSProviderConfig) -> None:
        """Test async context manager support."""
        async with JWKSProvider(config=jwks_config):
            pass
        # Provider should be closed after exiting context


class TestJWTVerification:
    """Tests for JWT verification utilities."""

    @pytest.fixture
    def jwks_provider(self) -> JWKSProvider:
        """Create mock JWKS provider."""
        provider = MagicMock(spec=JWKSProvider)
        provider.get_jwks = AsyncMock(return_value=TEST_JWKS)
        return provider

    @pytest.fixture
    def jwt_config(self) -> JWTVerificationConfig:
        """Create JWT verification config."""
        return JWTVerificationConfig(
            audience="test-audience",
            issuer="test-issuer",
            algorithms=["RS256"],
            require_sub=True,
        )

    @pytest.mark.asyncio
    async def test_verify_jwt_with_jwks_success(
        self,
        jwks_provider: MagicMock,
        jwt_config: JWTVerificationConfig,
    ) -> None:
        """Test successful JWT verification."""
        with (
            patch("jose.jwt.get_unverified_header") as mock_get_header,
            patch("jose.jwt.decode") as mock_decode,
        ):
            mock_get_header.return_value = {"kid": "test-key-1"}
            mock_decode.return_value = {
                "sub": "user123",
                "aud": "test-audience",
                "iss": "test-issuer",
            }

            payload = await verify_jwt_with_jwks(
                token="test-token",
                jwks_provider=jwks_provider,
                config=jwt_config,
            )

            assert payload is not None
            assert payload.get("sub") == "user123"
            assert payload.get("aud") == "test-audience"

    @pytest.mark.asyncio
    async def test_verify_jwt_no_kid(
        self,
        jwks_provider: MagicMock,
        jwt_config: JWTVerificationConfig,
    ) -> None:
        """Test JWT verification fails when JWT has no kid."""
        with patch("jose.jwt.get_unverified_header") as mock_get_header:
            mock_get_header.return_value = {}

            with pytest.raises(JWTVerificationError):
                await verify_jwt_with_jwks(
                    token="invalid-token",
                    jwks_provider=jwks_provider,
                    config=jwt_config,
                )

    @pytest.mark.asyncio
    async def test_verify_jwt_key_not_found(
        self,
        jwks_provider: MagicMock,
        jwt_config: JWTVerificationConfig,
    ) -> None:
        """Test JWT verification fails when key not found in JWKS."""
        with patch("jose.jwt.get_unverified_header") as mock_get_header:
            mock_get_header.return_value = {"kid": "unknown-key"}

            with pytest.raises(JWTVerificationError):
                await verify_jwt_with_jwks(
                    token="test-token",
                    jwks_provider=jwks_provider,
                    config=jwt_config,
                )

    @pytest.mark.asyncio
    async def test_verify_jwt_no_sub(
        self,
        jwks_provider: MagicMock,
        jwt_config: JWTVerificationConfig,
    ) -> None:
        """Test JWT verification fails when subject is missing."""
        with (
            patch("jose.jwt.get_unverified_header") as mock_get_header,
            patch("jose.jwt.decode") as mock_decode,
        ):
            mock_get_header.return_value = {"kid": "test-key-1"}
            mock_decode.return_value = {
                "aud": "test-audience",
                "iss": "test-issuer",
            }

            with pytest.raises(JWTVerificationError):
                await verify_jwt_with_jwks(
                    token="test-token",
                    jwks_provider=jwks_provider,
                    config=jwt_config,
                )

    @pytest.mark.asyncio
    async def test_verify_jwt_expired_token(
        self,
        jwks_provider: MagicMock,
        jwt_config: JWTVerificationConfig,
    ) -> None:
        """Test JWT verification fails for expired tokens."""
        from jose.exceptions import ExpiredSignatureError

        with (
            patch("jose.jwt.get_unverified_header") as mock_get_header,
            patch("jose.jwt.decode") as mock_decode,
        ):
            mock_get_header.return_value = {"kid": "test-key-1"}
            mock_decode.side_effect = ExpiredSignatureError("Token expired")

            with pytest.raises(JWTVerificationError):
                await verify_jwt_with_jwks(
                    token="expired-token",
                    jwks_provider=jwks_provider,
                    config=jwt_config,
                )

    @pytest.mark.asyncio
    async def test_verify_jwt_invalid_signature(
        self,
        jwks_provider: MagicMock,
        jwt_config: JWTVerificationConfig,
    ) -> None:
        """Test JWT verification fails for invalid signature."""
        from jose import JWTError

        with (
            patch("jose.jwt.get_unverified_header") as mock_get_header,
            patch("jose.jwt.decode") as mock_decode,
        ):
            mock_get_header.return_value = {"kid": "test-key-1"}
            mock_decode.side_effect = JWTError("Invalid signature")

            with pytest.raises(JWTVerificationError):
                await verify_jwt_with_jwks(
                    token="invalid-token",
                    jwks_provider=jwks_provider,
                    config=jwt_config,
                )


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
