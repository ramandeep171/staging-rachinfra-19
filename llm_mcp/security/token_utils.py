"""Scoped HMAC/JWT-style token helpers for MCP gateways.

This module keeps the logic side-car so controllers can import the
validator without changing the database schema. It avoids external
dependencies by implementing a minimal JWT validator with constant-time
signature checks and nonce replay protection hooks.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Iterable, Mapping, MutableMapping, Sequence


class TokenValidationError(Exception):
    """Raised when token validation fails."""


def _b64url_decode(segment: str) -> bytes:
    padding = "=" * (-len(segment) % 4)
    return base64.urlsafe_b64decode(segment + padding)


def _pick_signing_key(
    keys: Sequence[Mapping[str, str]], kid: str | None
) -> Mapping[str, str]:
    if kid:
        for key in keys:
            if key.get("kid") == kid:
                return key
    return keys[0]


def _load_token_sections(raw_token: str) -> tuple[bytes, dict, dict, bytes]:
    try:
        header_b64, payload_b64, signature_b64 = raw_token.split(".")
    except ValueError as exc:  # noqa: B904 - keep error detail
        raise TokenValidationError("Token must contain header.payload.signature") from exc

    try:
        header = json.loads(_b64url_decode(header_b64))
        payload = json.loads(_b64url_decode(payload_b64))
        signature = _b64url_decode(signature_b64)
    except Exception as exc:  # noqa: BLE001 - downstream handles sanitized error
        raise TokenValidationError("Token sections are not valid base64url JSON") from exc

    signing_input = f"{header_b64}.{payload_b64}".encode()
    return signing_input, header, payload, signature


def _ensure_nonce(
    cache: MutableMapping[str, int], cache_key: str, ttl_seconds: int
) -> None:
    # Simple TTL cache contract; callers can wrap Redis or any mapping with expiry.
    now = int(time.time())
    # Drop expired entries if the cache stores timestamps.
    expired = []
    for key, expires_at in list(cache.items()):
        if expires_at and expires_at <= now:
            expired.append(key)
    for key in expired:
        cache.pop(key, None)

    if cache_key in cache:
        raise TokenValidationError("Replay detected for nonce")
    cache[cache_key] = now + ttl_seconds


def validate_scoped_token(
    raw_token: str,
    *,
    signing_keys: Sequence[Mapping[str, str]],
    required_scopes: Iterable[str],
    nonce: str,
    nonce_cache: MutableMapping[str, int],
    leeway: int = 30,
) -> dict:
    """Validate a scoped, expiring HMAC token with nonce replay protection.

    Parameters
    ----------
    raw_token: The serialized token string.
    signing_keys: List of key dicts `{"kid": "2024-12", "secret": "..."}` with the first
                  item considered primary if no matching `kid` is found.
    required_scopes: Iterable of scopes required for the current request.
    nonce: One-time nonce provided by the caller (e.g., `X-MCP-Nonce` header).
    nonce_cache: Mutable mapping acting as a TTL cache. In production this should wrap
                 Redis `setnx`/`expire` semantics. The validator performs a best-effort
                 TTL purge when using in-memory maps for tests.
    leeway: Seconds of clock skew allowed when evaluating `exp`.

    Returns
    -------
    dict: Decoded token payload if validation succeeds.
    """

    if not signing_keys:
        raise TokenValidationError("No signing keys configured")

    signing_input, header, payload, signature = _load_token_sections(raw_token)
    alg = header.get("alg")
    if alg != "HS256":
        raise TokenValidationError("Unsupported alg; expected HS256")

    key = _pick_signing_key(signing_keys, header.get("kid"))
    secret = key.get("secret")
    if not secret:
        raise TokenValidationError("Signing secret missing")

    expected = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
    if not hmac.compare_digest(expected, signature):
        raise TokenValidationError("Signature mismatch")

    exp = payload.get("exp")
    if not isinstance(exp, (int, float)):
        raise TokenValidationError("exp claim missing")
    if time.time() > exp + leeway:
        raise TokenValidationError("Token expired")

    if nonce:
        cache_key = f"mcp:nonce:{payload.get('sub', 'anon')}:{nonce}"
        _ensure_nonce(nonce_cache, cache_key, ttl_seconds=300)

    scopes = payload.get("scope") or []
    if isinstance(scopes, str):
        scopes = [scopes]
    missing = [scope for scope in required_scopes if scope not in scopes]
    if missing:
        raise TokenValidationError(f"Missing scopes: {','.join(missing)}")

    return payload
