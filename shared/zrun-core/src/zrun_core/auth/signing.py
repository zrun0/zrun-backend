"""JWT token signing utilities for internal services.

This module provides JWT generation and JWKS building capabilities
for services that need to issue internal JWT tokens.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from jose import jwk, jwt
from structlog import get_logger

logger = get_logger()


def generate_token(
    private_key: str,
    issuer: str,
    audience: str,
    subject: str,
    expiration_seconds: int,
    key_id: str | None = None,
    additional_claims: dict[str, Any] | None = None,
) -> str:
    """Generate a JWT token using RS256.

    Args:
        private_key: PEM-formatted private key for signing.
        issuer: Issuer claim (e.g., "zrun-bff").
        audience: Audience claim (e.g., "zrun-services").
        subject: Subject claim (user ID).
        expiration_seconds: Token lifetime in seconds.
        key_id: Key ID for JWKS (kid header).
        additional_claims: Additional claims to include in token.

    Returns:
        Encoded JWT token string.

    Raises:
        ValueError: If private_key is invalid.
    """
    now = datetime.now(UTC)
    exp = now + timedelta(seconds=expiration_seconds)
    nbf = now

    payload: dict[str, Any] = {
        "iss": issuer,
        "aud": audience,
        "sub": subject,
        "exp": exp,
        "nbf": nbf,
        "iat": now,
    }

    if additional_claims:
        payload.update(additional_claims)

    headers: dict[str, Any] = {}
    if key_id:
        headers["kid"] = key_id

    try:
        token = jwt.encode(
            claims=payload,
            key=private_key,
            algorithm="RS256",
            headers=headers,
        )
        logger.debug("jwt_generated", sub=subject, exp=exp.isoformat())
        return token
    except Exception as e:
        msg = f"Failed to generate JWT token: {e}"
        logger.error("jwt_generation_failed", error=str(e))
        raise ValueError(msg) from e


def get_public_key_pem(private_key_pem: str) -> str:
    """Extract public key in PEM format from private key.

    Args:
        private_key_pem: PEM-formatted private key.

    Returns:
        PEM-formatted public key string.

    Raises:
        ValueError: If private_key_pem is invalid.
    """
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.serialization import load_pem_private_key

        private_key = load_pem_private_key(private_key_pem.encode(), password=None)
        return (
            private_key.public_key()
            .public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
            .decode("utf-8")
        )
    except Exception as e:
        msg = f"Failed to extract public key: {e}"
        logger.error("public_key_extraction_failed", error=str(e))
        raise ValueError(msg) from e


def get_public_key(private_key_pem: str) -> Any:
    """Extract public key from private key for JWKS endpoint.

    Args:
        private_key_pem: PEM-formatted private key.

    Returns:
        RSA public key object (jwk.Key).

    Raises:
        ValueError: If private_key_pem is invalid.
    """
    try:
        private_key = jwk.construct(private_key_pem, algorithm="RS256")
        return private_key.public_key()
    except Exception as e:
        msg = f"Failed to extract public key: {e}"
        logger.error("public_key_extraction_failed", error=str(e))
        raise ValueError(msg) from e


def build_jwks(
    public_key: Any,
    key_id: str,
) -> dict[str, Any]:
    """Build JWKS response for public key.

    Args:
        public_key: RSA public key object (jwk.Key).
        key_id: Key ID for JWKS (kid).

    Returns:
        JWKS dictionary with keys list.

    Example:
        >>> public_key = get_public_key(private_key_pem)
        >>> jwks = build_jwks(public_key, "key-1")
        >>> {"keys": [{"kty": "RSA", "kid": "key-1", "use": "sig", "n": "...", "e": "..."}]}
    """
    public_jwk = public_key.to_dict()

    return {
        "keys": [
            {
                "kty": public_jwk.get("kty", "RSA"),
                "kid": key_id,
                "use": "sig",
                "n": public_jwk["n"],
                "e": public_jwk.get("e", "AQAB"),
            }
        ]
    }


def decode_token(
    token: str,
    public_key: str,
    audience: str,
    issuer: str,
) -> dict[str, Any] | None:
    """Decode and validate JWT token using public key.

    This is primarily used for testing and debugging. Production services
    should use the JWKS-based validation in zrun_core.auth.AuthInterceptor.

    Args:
        token: JWT token string.
        public_key: PEM-formatted public key.
        audience: Expected audience claim.
        issuer: Expected issuer claim.

    Returns:
        Decoded token payload if valid, None otherwise.
    """
    from jose.exceptions import JWTError

    try:
        payload = jwt.decode(
            token=token,
            key=public_key,
            algorithms=["RS256"],
            audience=audience,
            issuer=issuer,
        )
        logger.debug("jwt_decoded", sub=payload.get("sub"))
        return payload
    except JWTError as e:
        logger.warning("jwt_decode_failed", error=str(e))
        return None


__all__ = [
    "generate_token",
    "get_public_key",
    "get_public_key_pem",
    "build_jwks",
    "decode_token",
]
