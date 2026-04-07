"""Unit tests for enhanced scope validation (require_any, require_all)."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi import Depends, FastAPI, status
from fastapi.testclient import TestClient

from zrun_bff.auth.auth_deps import require_all, require_any, require_scope
from zrun_bff.auth.constants import Scope
from zrun_bff.auth.tokens import generate_token_pair
from zrun_bff.config import BFFConfig, get_config


@pytest.fixture
def test_key_files() -> Generator[str]:
    """Create temporary RSA key pair and configure environment."""
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

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

        original = os.environ.get("JWT_PRIVATE_KEY_PATH")
        os.environ["JWT_PRIVATE_KEY_PATH"] = str(private_key_path)
        get_config.cache_clear()  # Force config reload with new key path

        try:
            yield tmpdir
        finally:
            if original is not None:
                os.environ["JWT_PRIVATE_KEY_PATH"] = original
            else:
                os.environ.pop("JWT_PRIVATE_KEY_PATH", None)
            get_config.cache_clear()


def _make_client(dependency: object, return_sub: bool = False) -> tuple[FastAPI, TestClient]:
    """Create a minimal FastAPI app with a single protected GET /test endpoint."""
    app = FastAPI()

    if return_sub:

        @app.get("/test")
        async def handler(user: dict = dependency) -> dict:
            return {"user_id": user["sub"]}
    else:

        @app.get("/test")
        async def handler(user: dict = dependency) -> dict:  # type: ignore[misc]
            return {"status": "ok"}

    return app, TestClient(app, raise_server_exceptions=False)


@pytest.mark.usefixtures("test_key_files")
class TestRequireAny:
    """Tests for require_any (OR mode) scope validation."""

    def test_require_any_grants_access_with_one_matching_scope(self) -> None:
        """require_any grants access when user has one of the required scopes."""
        _, client = _make_client(
            Depends(require_any(Scope.PDA_READ, Scope.WEB_ADMIN)), return_sub=True
        )
        config = BFFConfig()
        token_pair = generate_token_pair(config=config, user_id="test_user", scopes="pda:read")

        response = client.get(
            "/test", headers={"Authorization": f"Bearer {token_pair.access_token}"}
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["user_id"] == "test_user"

    def test_require_any_denies_access_with_no_matching_scopes(self) -> None:
        """require_any denies access when user has none of the required scopes."""
        _, client = _make_client(Depends(require_any(Scope.PDA_READ, Scope.WEB_ADMIN)))
        config = BFFConfig()
        token_pair = generate_token_pair(config=config, user_id="test_user", scopes="mini:read")

        response = client.get(
            "/test", headers={"Authorization": f"Bearer {token_pair.access_token}"}
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_require_any_grants_access_with_all_matching_scopes(self) -> None:
        """require_any grants access when user has all of the required scopes."""
        _, client = _make_client(Depends(require_any(Scope.PDA_READ, Scope.PDA_WRITE)))
        config = BFFConfig()
        token_pair = generate_token_pair(
            config=config, user_id="test_user", scopes="pda:read pda:write"
        )

        response = client.get(
            "/test", headers={"Authorization": f"Bearer {token_pair.access_token}"}
        )

        assert response.status_code == status.HTTP_200_OK


@pytest.mark.usefixtures("test_key_files")
class TestRequireAll:
    """Tests for require_all (AND mode) scope validation."""

    def test_require_all_grants_access_with_all_required_scopes(self) -> None:
        """require_all grants access when user has all required scopes."""
        _, client = _make_client(
            Depends(require_all(Scope.PDA_READ, Scope.PDA_WRITE)), return_sub=True
        )
        config = BFFConfig()
        token_pair = generate_token_pair(
            config=config, user_id="test_user", scopes="pda:read pda:write"
        )

        response = client.get(
            "/test", headers={"Authorization": f"Bearer {token_pair.access_token}"}
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["user_id"] == "test_user"

    def test_require_all_denies_access_with_missing_scope(self) -> None:
        """require_all denies access when user is missing a required scope."""
        _, client = _make_client(Depends(require_all(Scope.PDA_READ, Scope.PDA_WRITE)))
        config = BFFConfig()
        token_pair = generate_token_pair(config=config, user_id="test_user", scopes="pda:read")

        response = client.get(
            "/test", headers={"Authorization": f"Bearer {token_pair.access_token}"}
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "pda:write" in response.json()["detail"]

    def test_require_all_denies_access_with_no_matching_scopes(self) -> None:
        """require_all denies access when user has none of the required scopes."""
        _, client = _make_client(Depends(require_all(Scope.PDA_READ, Scope.PDA_WRITE)))
        config = BFFConfig()
        token_pair = generate_token_pair(config=config, user_id="test_user", scopes="web:admin")

        response = client.get(
            "/test", headers={"Authorization": f"Bearer {token_pair.access_token}"}
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_require_all_with_single_scope(self) -> None:
        """require_all works with a single scope."""
        _, client = _make_client(Depends(require_all(Scope.PDA_READ)))
        config = BFFConfig()
        token_pair = generate_token_pair(config=config, user_id="test_user", scopes="pda:read")

        response = client.get(
            "/test", headers={"Authorization": f"Bearer {token_pair.access_token}"}
        )

        assert response.status_code == status.HTTP_200_OK


@pytest.mark.usefixtures("test_key_files")
class TestRequireScopeBackwardCompatibility:
    """Tests for backward compatibility of require_scope."""

    def test_require_scope_uses_or_mode_by_default(self) -> None:
        """require_scope uses OR mode — one matching scope is enough."""
        _, client = _make_client(Depends(require_scope(Scope.PDA_READ, Scope.WEB_ADMIN)))
        config = BFFConfig()
        token_pair = generate_token_pair(config=config, user_id="test_user", scopes="pda:read")

        response = client.get(
            "/test", headers={"Authorization": f"Bearer {token_pair.access_token}"}
        )

        assert response.status_code == status.HTTP_200_OK

    def test_require_scope_with_single_scope(self) -> None:
        """require_scope works with a single scope."""
        _, client = _make_client(Depends(require_scope(Scope.PDA_READ)))
        config = BFFConfig()
        token_pair = generate_token_pair(config=config, user_id="test_user", scopes="pda:read")

        response = client.get(
            "/test", headers={"Authorization": f"Bearer {token_pair.access_token}"}
        )

        assert response.status_code == status.HTTP_200_OK

    def test_require_scope_denies_without_required_scope(self) -> None:
        """require_scope denies access when user lacks the required scope."""
        _, client = _make_client(Depends(require_scope(Scope.PDA_READ)))
        config = BFFConfig()
        token_pair = generate_token_pair(config=config, user_id="test_user", scopes="web:admin")

        response = client.get(
            "/test", headers={"Authorization": f"Bearer {token_pair.access_token}"}
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN


class TestScopeValidationEdgeCases:
    """Tests for edge cases in scope validation."""

    def test_require_any_raises_error_with_no_scopes(self) -> None:
        """require_any raises ValueError when no scopes specified."""
        with pytest.raises(ValueError, match="At least one scope"):
            require_any()

    def test_require_all_raises_error_with_no_scopes(self) -> None:
        """require_all raises ValueError when no scopes specified."""
        with pytest.raises(ValueError, match="At least one scope"):
            require_all()

    def test_require_scope_raises_error_with_no_scopes(self) -> None:
        """require_scope raises ValueError when no scopes specified."""
        with pytest.raises(ValueError, match="At least one scope"):
            require_scope()
