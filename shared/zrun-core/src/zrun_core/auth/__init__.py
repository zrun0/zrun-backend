"""Authentication utilities for zrun services."""

from __future__ import annotations

from zrun_core.auth.auth import USER_ID_CTX_KEY, AuthInterceptor
from zrun_core.auth.jwks import JWKSProvider, JWKSProviderConfig, JWKSProviderError
from zrun_core.auth.protocols import JWKSProviderProtocol, JWTVerifierProtocol
from zrun_core.auth.signing import (
    build_jwks,
    decode_token,
    generate_token,
    get_public_key,
    get_public_key_pem,
)
from zrun_core.auth.verification import (
    JWTVerificationConfig,
    JWTVerificationError,
    verify_jwt_with_jwks,
)

__all__ = [
    # Auth interceptor
    "AuthInterceptor",
    "USER_ID_CTX_KEY",
    # JWKS provider
    "JWKSProvider",
    "JWKSProviderConfig",
    "JWKSProviderError",
    "JWKSProviderProtocol",
    # JWT signing
    "generate_token",
    "get_public_key",
    "get_public_key_pem",
    "build_jwks",
    "decode_token",
    # JWT verification
    "JWTVerificationConfig",
    "JWTVerificationError",
    "JWTVerifierProtocol",
    "verify_jwt_with_jwks",
]
