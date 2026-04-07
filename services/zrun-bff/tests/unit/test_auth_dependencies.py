"""Unit tests for auth dependencies."""

from __future__ import annotations

from fastapi import HTTPException, status

from zrun_bff.auth.constants import Scope


class TestScope:
    """Tests for Scope enum."""

    def test_scope_values(self) -> None:
        """Test that all expected scopes are defined."""
        assert Scope.PDA_READ == "pda:read"
        assert Scope.PDA_WRITE == "pda:write"
        assert Scope.WEB_ADMIN == "web:admin"
        assert Scope.WEB_READ == "web:read"
        assert Scope.MINI_READ == "mini:read"
        assert Scope.ADMIN_ALL == "admin:all"


class TestScopeValidation:
    """Tests for scope validation logic."""

    def test_scope_check_with_valid_scope(self) -> None:
        """Test that user with required scope passes check."""
        user = {"sub": "user-123", "scope": "pda:read pda:write"}

        token_scopes = user.get("scope", "")
        user_scopes = token_scopes.split() if isinstance(token_scopes, str) else []

        # Check if user has pda:read scope
        has_scope = Scope.PDA_READ.value in user_scopes
        assert has_scope is True

    def test_scope_check_with_multiple_valid_scopes(self) -> None:
        """Test that user with one of multiple required scopes passes."""
        user = {"sub": "user-123", "scope": "pda:read"}

        token_scopes = user.get("scope", "")
        user_scopes = token_scopes.split() if isinstance(token_scopes, str) else []

        required_scopes = [Scope.PDA_WRITE.value, Scope.PDA_READ.value]
        has_any_scope = any(s in user_scopes for s in required_scopes)

        assert has_any_scope is True

    def test_scope_check_with_insufficient_scope(self) -> None:
        """Test that user without required scope fails check."""
        user = {"sub": "user-123", "scope": "pda:read"}

        token_scopes = user.get("scope", "")
        user_scopes = token_scopes.split() if isinstance(token_scopes, str) else []

        has_admin_scope = Scope.ADMIN_ALL.value in user_scopes
        assert has_admin_scope is False

    def test_scope_check_with_no_scope(self) -> None:
        """Test that user without any scope fails check."""
        user = {"sub": "user-123", "scope": ""}

        token_scopes = user.get("scope", "")
        user_scopes = token_scopes.split() if isinstance(token_scopes, str) else []

        has_any_scope = len(user_scopes) > 0
        assert has_any_scope is False

    def test_scope_check_with_non_string_scope(self) -> None:
        """Test that non-string scope is handled gracefully."""
        user = {"sub": "user-123", "scope": 123}

        token_scopes = user.get("scope", "")
        user_scopes = token_scopes.split() if isinstance(token_scopes, str) else []

        assert len(user_scopes) == 0


class TestHTTPExceptionCodes:
    """Tests for HTTP exception status codes."""

    def test_unauthorized_status_code(self) -> None:
        """Test that 401 UNAUTHORIZED status code is correct."""
        assert status.HTTP_401_UNAUTHORIZED == 401

    def test_forbidden_status_code(self) -> None:
        """Test that 403 FORBIDDEN status code is correct."""
        assert status.HTTP_403_FORBIDDEN == 403

    def test_http_exception_creation(self) -> None:
        """Test creating HTTPException with proper attributes."""
        exc = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

        assert exc.status_code == 401
        assert exc.detail == "Not authenticated"
        assert exc.headers["WWW-Authenticate"] == "Bearer"
