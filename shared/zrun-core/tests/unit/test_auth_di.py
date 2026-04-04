"""Tests demonstrating dependency injection with Protocol interfaces.

These tests show how Protocol interfaces enable flexible testing
and dependency injection.
"""

from __future__ import annotations

import pytest

from zrun_core.auth.protocols import JWKSProviderProtocol
from zrun_core.auth.auth import AuthInterceptor


class MockJWKSProvider:
    """Mock JWKS provider for testing.

    This mock implements JWKSProviderProtocol for testing purposes.
    """

    def __init__(self) -> None:
        self._closed = False
        self.call_count = 0
        self._jwks = {
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

    async def get_jwks(self) -> dict[str, object]:
        """Return mock JWKS data."""
        self.call_count += 1
        return self._jwks

    def get_key_by_kid(self, kid: str) -> dict[str, object] | None:
        """Get a key by kid."""
        for key in self._jwks.get("keys", []):
            if key.get("kid") == kid:
                return key
        return None

    async def close(self) -> None:
        """Mark provider as closed."""
        self._closed = True

    async def __aenter__(self) -> MockJWKSProvider:
        """Async context manager entry."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        """Async context manager exit."""
        await self.close()


class TestDependencyInjection:
    """Tests demonstrating dependency injection benefits."""

    @pytest.mark.asyncio
    async def test_auth_interceptor_with_mock_provider(self) -> None:
        """Test AuthInterceptor with injected mock provider.

        This demonstrates how Protocol interfaces enable easy testing
        without needing to set up real HTTP servers.
        """
        # Create mock provider
        mock_provider = MockJWKSProvider()

        # Create interceptor with dependency injection
        interceptor = AuthInterceptor(
            jwks_provider=mock_provider,  # Inject mock provider
            audience="test-audience",
            issuer="test-issuer",
        )

        # Verify interceptor uses the mock provider
        assert interceptor._jwks_provider is mock_provider
        assert not interceptor._owned_provider  # We don't own the mock

        # Cleanup
        await interceptor.close()

        # Mock provider should NOT be closed (we don't own it)
        assert not mock_provider._closed

    @pytest.mark.asyncio
    async def test_auth_interceptor_owns_created_provider(self) -> None:
        """Test that AuthInterceptor owns providers it creates.

        This demonstrates lifecycle management.
        """
        # Create interceptor with URL (it creates its own provider)
        interceptor = AuthInterceptor(
            jwks_url="https://example.com/jwks.json",
            audience="test-audience",
            issuer="test-issuer",
        )

        # Verify interceptor owns the provider
        assert interceptor._owned_provider

        # Cleanup should close the provider
        await interceptor.close()

    @pytest.mark.asyncio
    async def test_mock_provider_isolation(self) -> None:
        """Test that mock provider provides test isolation.

        This demonstrates how Protocol interfaces enable
        isolated, deterministic testing.
        """
        mock_provider = MockJWKSProvider()

        # Verify initial state
        assert mock_provider.call_count == 0

        # Call get_jwks multiple times
        await mock_provider.get_jwks()
        await mock_provider.get_jwks()
        await mock_provider.get_jwks()

        # Verify call count
        assert mock_provider.call_count == 3

        # Each call returns the same data (deterministic)
        jwks1 = await mock_provider.get_jwks()
        jwks2 = await mock_provider.get_jwks()
        assert jwks1 == jwks2

    @pytest.mark.asyncio
    async def test_protocol_compliance(self) -> None:
        """Test that mock provider complies with Protocol.

        This demonstrates that any object implementing
        the Protocol interface can be used.
        """
        mock_provider = MockJWKSProvider()

        # Verify mock provider implements the protocol
        assert isinstance(mock_provider, JWKSProviderProtocol)

        # Can be used wherever JWKSProviderProtocol is expected
        async def use_provider(provider: JWKSProviderProtocol) -> dict[str, object]:
            """Function expecting JWKSProviderProtocol."""
            return await provider.get_jwks()

        result = await use_provider(mock_provider)
        assert "keys" in result


class TestProtocolBenefits:
    """Tests demonstrating benefits of Protocol interfaces."""

    @pytest.mark.asyncio
    async def test_swappable_implementations(self) -> None:
        """Test that implementations can be swapped.

        This demonstrates the Strategy Pattern enabled by Protocols.
        """

        # Fast mock for testing
        fast_mock = MockJWKSProvider()

        # Both can be used interchangeably
        async def verify_with_provider(provider: JWKSProviderProtocol) -> bool:
            """Function that works with any provider implementation."""
            jwks = await provider.get_jwks()
            return "keys" in jwks

        # Works with mock
        assert await verify_with_provider(fast_mock)

    @pytest.mark.asyncio
    async def test_type_safety(self) -> None:
        """Test that Protocols provide type safety.

        This demonstrates how Protocols enable static type checking.
        """

        async def process_provider(provider: JWKSProviderProtocol) -> int:
            """Function with typed parameter."""
            jwks = await provider.get_jwks()
            return len(jwks.get("keys", []))

        mock = MockJWKSProvider()
        result = await process_provider(mock)
        assert result == 1

        # Type checkers would verify that only objects
        # implementing JWKSProviderProtocol can be passed

    @pytest.mark.asyncio
    async def test_duck_typing_with_protocols(self) -> None:
        """Test that Protocols enable duck typing.

        This demonstrates structural subtyping - objects with
        matching methods are compatible even without inheritance.
        """

        # Create a simple object with matching methods
        class SimpleProvider:
            async def get_jwks(self) -> dict[str, object]:
                return {"keys": []}

            async def close(self) -> None:
                pass

        # It works with the Protocol because it has the right structure
        async def use_provider(provider: JWKSProviderProtocol) -> bool:
            jwks = await provider.get_jwks()
            return len(jwks["keys"]) == 0

        simple = SimpleProvider()
        result = await use_provider(simple)
        assert result
