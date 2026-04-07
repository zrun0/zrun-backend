"""Authentication module for BFF service."""

from zrun_bff.auth.auth_deps import (
    get_current_user,
    get_optional_user,
    require_all,
    require_any,
    require_scope,
)
from zrun_bff.auth.constants import Scope
from zrun_bff.auth.middleware import UserContextMiddleware
from zrun_bff.auth.tokens import (
    TokenClaims,
    TokenPair,
    generate_token_pair,
    refresh_access_token,
    verify_access_token,
)

__all__ = [
    # Constants
    "Scope",
    # Middleware
    "UserContextMiddleware",
    # Tokens
    "TokenClaims",
    "TokenPair",
    "generate_token_pair",
    "refresh_access_token",
    "verify_access_token",
    # Dependencies
    "get_current_user",
    "get_optional_user",
    "require_scope",
    "require_any",
    "require_all",
]
