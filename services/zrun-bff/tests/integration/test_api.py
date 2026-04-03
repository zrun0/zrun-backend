"""Integration tests for zrun-bff FastAPI application."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

if TYPE_CHECKING:
    from fastapi import FastAPI
    from zrun_bff.config import BFFConfig


@pytest.fixture
def test_config() -> BFFConfig:
    """Create a test BFF configuration."""
    from zrun_bff.config import BFFConfig

    return BFFConfig(
        env="dev",
        port=8000,
        jwt_private_key_path="",
        casdoor_client_id="test-client-id",
        casdoor_client_secret="test-secret",
        casdoor_redirect_uri="http://localhost:8000/auth/callback",
        casdoor_authorization_endpoint="http://localhost:8080/oauth/authorize",
        casdoor_token_endpoint="http://localhost:8080/oauth/token",
        cors_origins=["http://localhost:3000"],
    )


@pytest.fixture
def test_app(test_config: BFFConfig) -> FastAPI:
    """Create a test FastAPI application."""
    from zrun_bff.main import create_app

    return create_app(test_config)


@pytest.fixture
def client(test_app: FastAPI) -> TestClient:
    """Create a test client for the FastAPI application."""
    return TestClient(test_app)


class TestHealthEndpoint:
    """Tests for /health endpoint."""

    def test_health_check_returns_healthy_status(self, client: TestClient) -> None:
        """Test that health check returns healthy status."""
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "zrun-bff"


class TestLoginRedirect:
    """Tests for /auth/login endpoint."""

    def test_login_redirect_returns_302(self, client: TestClient) -> None:
        """Test that login endpoint returns redirect."""
        response = client.get("/auth/login", follow_redirects=False)

        assert response.status_code == 302
        location = response.headers.get("location")
        assert location is not None
        assert "oauth" in location or "authorize" in location

    def test_login_redirect_contains_oauth_params(self, client: TestClient) -> None:
        """Test that login redirect includes OAuth2 parameters."""
        response = client.get("/auth/login", follow_redirects=False)

        location = response.headers.get("location", "")
        assert "response_type=code" in location
        assert "redirect_uri=" in location


class TestCORSMiddleware:
    """Tests for CORS middleware."""

    def test_options_request_handled(self, client: TestClient) -> None:
        """Test OPTIONS preflight request is handled."""
        response = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )

        assert response.status_code in (200, 204)

    def test_get_request_succeeds(self, client: TestClient) -> None:
        """Test GET request with CORS headers."""
        response = client.get(
            "/health",
            headers={"Origin": "http://localhost:3000"},
        )

        assert response.status_code == 200


class TestApplicationStructure:
    """Tests for application structure and routes."""

    def test_app_metadata(self, test_app) -> None:
        """Test FastAPI app has correct metadata."""
        assert test_app.title == "Zrun BFF"
        assert test_app.version == "0.1.0-dev"
        assert any(route.path == "/health" for route in test_app.routes)

    def test_auth_routes_registered(self, test_app) -> None:
        """Test authentication routes are registered."""
        routes = {route.path for route in test_app.routes if hasattr(route, "path")}

        assert "/auth/login" in routes
        assert "/auth/callback" in routes
        assert "/.well-known/jwks.json" in routes


class TestErrorHandling:
    """Tests for error response handling."""

    def test_404_returns_json(self, client: TestClient) -> None:
        """Test 404 returns JSON error."""
        response = client.get("/non-existent")

        assert response.status_code == 404
        assert "application/json" in response.headers.get("content-type", "")

    def test_405_method_not_allowed(self, client: TestClient) -> None:
        """Test 405 for wrong HTTP method."""
        response = client.post("/health")

        assert response.status_code == 405

    def test_invalid_route_returns_404(self, client: TestClient) -> None:
        """Test invalid route returns 404."""
        response = client.get("/api/invalid-route")

        assert response.status_code == 404


class TestJWKSEndpoint:
    """Tests for JWKS endpoint."""

    def test_jwks_endpoint_exists(self, test_app) -> None:
        """Test JWKS endpoint is registered."""
        routes = [route.path for route in test_app.routes if hasattr(route, "path")]
        assert "/.well-known/jwks.json" in routes


class TestOAuthCallbackBasic:
    """Basic tests for OAuth callback endpoint."""

    def test_callback_endpoint_exists(self, test_app) -> None:
        """Test OAuth callback endpoint is registered."""
        routes = [route.path for route in test_app.routes if hasattr(route, "path")]
        assert "/auth/callback" in routes

    def test_callback_requires_code_param(self, client: TestClient) -> None:
        """Test callback requires code parameter."""
        response = client.get("/auth/callback")

        # Should fail without code parameter
        assert response.status_code in (400, 401, 422)
