"""Unit tests for JWKS endpoint."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from zrun_bff.config import get_config


@pytest.fixture
def test_key_files() -> Generator[str]:
    """Create temporary key files for testing."""
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization

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

    with tempfile.TemporaryDirectory() as tmpdir:
        private_key_path = Path(tmpdir) / "private.pem"
        private_key_path.write_text(private_pem)

        original_private = os.environ.get("JWT_PRIVATE_KEY_PATH")
        os.environ["JWT_PRIVATE_KEY_PATH"] = str(private_key_path)
        get_config.cache_clear()  # Force config reload with new key path

        try:
            yield tmpdir
        finally:
            if original_private:
                os.environ["JWT_PRIVATE_KEY_PATH"] = original_private
            else:
                os.environ.pop("JWT_PRIVATE_KEY_PATH", None)
            get_config.cache_clear()  # Clean up cache


@pytest.fixture
def app_with_test_keys(test_key_files: str) -> TestClient:  # noqa: ARG001
    """Create test app with temporary key files."""
    # test_key_files fixture establishes env var + cache_clear ordering
    from zrun_bff.main import create_app

    app = create_app()
    return TestClient(app)


@pytest.mark.usefixtures("test_key_files")
class TestJWKSEndpoint:
    """Tests for JWKS endpoint."""

    def test_jwks_endpoint_returns_valid_structure(self, app_with_test_keys: TestClient) -> None:
        """Test that JWKS endpoint returns valid JWKS structure."""
        response = app_with_test_keys.get("/.well-known/jwks.json")

        assert response.status_code == 200
        data = response.json()

        assert "keys" in data
        assert isinstance(data["keys"], list)
        assert len(data["keys"]) == 1

        key = data["keys"][0]
        assert key["kty"] == "RSA"
        assert "kid" in key
        assert key["use"] == "sig"

    def test_jwks_endpoint_includes_configured_key_id(self, app_with_test_keys: TestClient) -> None:
        """Test that JWKS endpoint includes configured key ID."""
        response = app_with_test_keys.get("/.well-known/jwks.json")

        assert response.status_code == 200
        data = response.json()

        key = data["keys"][0]
        assert key["kid"] == get_config().jwt_key_id

    def test_jwks_endpoint_allows_caching(self, app_with_test_keys: TestClient) -> None:
        """Test that JWKS endpoint allows caching."""
        response1 = app_with_test_keys.get("/.well-known/jwks.json")
        assert response1.status_code == 200
        assert response1.headers.get("content-type") == "application/json"

    def test_jwks_endpoint_returns_json_content_type(self, app_with_test_keys: TestClient) -> None:
        """Test that JWKS endpoint returns JSON content type."""
        response = app_with_test_keys.get("/.well-known/jwks.json")

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json"


@pytest.mark.usefixtures("test_key_files")
class TestJWKSIntegration:
    """Integration tests for JWKS endpoint."""

    def test_jwks_endpoint_works_with_oauth_flow(self, app_with_test_keys: TestClient) -> None:
        """Test that JWKS endpoint is accessible after OAuth flow."""
        health_response = app_with_test_keys.get("/health")
        assert health_response.status_code == 200

        jwks_response = app_with_test_keys.get("/.well-known/jwks.json")
        assert jwks_response.status_code == 200

    def test_jwks_endpoint_serves_public_key_only(self, app_with_test_keys: TestClient) -> None:
        """Test that JWKS endpoint only exposes public key."""
        response = app_with_test_keys.get("/.well-known/jwks.json")
        assert response.status_code == 200

        data = response.json()

        # Verify private key fields are absent
        for key in data.get("keys", []):
            assert "d" not in key
            assert "p" not in key


class TestJWKSEdgeCases:
    """Tests for JWKS endpoint edge cases."""

    def test_jwks_endpoint_returns_404_for_invalid_path(
        self, app_with_test_keys: TestClient
    ) -> None:
        """Test that invalid JWKS path returns 404."""
        response = app_with_test_keys.get("/.well-known/jwks.json/invalid")
        assert response.status_code == 404

    def test_jwks_endpoint_does_not_leak_private_key(self, app_with_test_keys: TestClient) -> None:
        """Test that private key material is never exposed."""
        response = app_with_test_keys.get("/.well-known/jwks.json")
        assert response.status_code == 200

        data = response.json()
        key = data["keys"][0]

        # Verify all required fields are present
        assert "kty" in key
        assert "kid" in key
        assert "use" in key
        assert "n" in key
        assert "e" in key

        # Verify private key fields are absent
        private_key_fields = ["d", "p", "q", "dp", "dq", "qi"]
        for field in private_key_fields:
            assert field not in key
