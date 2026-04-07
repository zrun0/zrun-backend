"""Unit tests for JWT token utilities."""

from __future__ import annotations

from unittest.mock import MagicMock

from zrun_core.auth import build_jwks


class TestBuildJwks:
    """Tests for build_jwks function."""

    def test_build_jwks_response(self) -> None:
        """Test building JWKS response."""
        mock_public_key = MagicMock()
        mock_public_key.to_dict.return_value = {
            "kty": "RSA",
            "n": "test-modulus",
            "e": "AQAB",
        }

        jwks = build_jwks(mock_public_key, "key-1")

        assert "keys" in jwks
        assert len(jwks["keys"]) == 1
        assert jwks["keys"][0]["kid"] == "key-1"
        assert jwks["keys"][0]["use"] == "sig"
        assert jwks["keys"][0]["kty"] == "RSA"
        assert jwks["keys"][0]["n"] == "test-modulus"

    def test_build_jwks_with_custom_key_id(self) -> None:
        """Test building JWKS with custom key ID."""
        mock_public_key = MagicMock()
        mock_public_key.to_dict.return_value = {
            "kty": "RSA",
            "n": "another-modulus",
            "e": "AQAB",
        }

        jwks = build_jwks(mock_public_key, "custom-key-2")

        assert jwks["keys"][0]["kid"] == "custom-key-2"
        assert jwks["keys"][0]["n"] == "another-modulus"


class TestJWKSStructure:
    """Tests for JWKS response structure."""

    def test_jwks_has_required_fields(self) -> None:
        """Test JWKS has all required fields."""
        mock_public_key = MagicMock()
        mock_public_key.to_dict.return_value = {
            "kty": "RSA",
            "n": "test-n",
            "e": "AQAB",
        }

        jwks = build_jwks(mock_public_key, "key-1")

        # Verify JWKS structure
        assert isinstance(jwks, dict)
        assert isinstance(jwks["keys"], list)
        assert len(jwks["keys"]) == 1

        key = jwks["keys"][0]
        assert "kty" in key
        assert "kid" in key
        assert "use" in key
        assert "n" in key
        assert "e" in key

    def test_jwks_use_sig_value(self) -> None:
        """Test JWKS use field is set to 'sig' (signing)."""
        mock_public_key = MagicMock()
        mock_public_key.to_dict.return_value = {
            "kty": "RSA",
            "n": "test-n",
            "e": "AQAB",
        }

        jwks = build_jwks(mock_public_key, "key-1")

        assert jwks["keys"][0]["use"] == "sig"


class TestScopeConstants:
    """Tests for JWT scope constants."""

    def test_scope_values_are_strings(self) -> None:
        """Test that scope values are valid strings."""
        from zrun_bff.auth.constants import Scope

        assert isinstance(Scope.PDA_READ, str)
        assert isinstance(Scope.PDA_WRITE, str)
        assert isinstance(Scope.WEB_ADMIN, str)
        assert isinstance(Scope.WEB_READ, str)
        assert isinstance(Scope.MINI_READ, str)
        assert isinstance(Scope.ADMIN_ALL, str)

    def test_scope_format(self) -> None:
        """Test that scope values follow OAuth2 format."""
        from zrun_bff.auth.constants import Scope

        # Scopes should be in format "resource:action"
        for scope in [Scope.PDA_READ, Scope.PDA_WRITE, Scope.WEB_ADMIN, Scope.WEB_READ]:
            parts = scope.split(":")
            assert len(parts) == 2
            assert parts[0]  # resource part exists
            assert parts[1]  # action part exists
