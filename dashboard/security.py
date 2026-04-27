"""Small no-dependency helpers for optional encrypted-at-rest JSON payloads.

The project runs with only Django installed in the course setup. For production,
set VOLLEYPILOT_STORAGE_ENCRYPTION_KEY to store selected analytics payloads as
an authenticated encrypted blob instead of plain JSON.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
from typing import Any


_KEY_ENV = "VOLLEYPILOT_STORAGE_ENCRYPTION_KEY"
_SALT = b"volleypilot-storage-v1"
_NONCE_SIZE = 16
_MAC_SIZE = 32


def storage_encryption_enabled() -> bool:
    return bool(os.environ.get(_KEY_ENV, "").strip())


def _derive_key(secret: str) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", secret.encode("utf-8"), _SALT, 200_000, dklen=32)


def _keystream(key: bytes, nonce: bytes, length: int) -> bytes:
    chunks = []
    counter = 0
    while sum(len(chunk) for chunk in chunks) < length:
        counter_bytes = counter.to_bytes(8, "big")
        chunks.append(hmac.new(key, nonce + counter_bytes, hashlib.sha256).digest())
        counter += 1
    return b"".join(chunks)[:length]


def encrypt_json(payload: dict[str, Any]) -> str:
    secret = os.environ.get(_KEY_ENV, "").strip()
    if not secret:
        raise RuntimeError(f"{_KEY_ENV} is not configured.")
    key = _derive_key(secret)
    nonce = secrets.token_bytes(_NONCE_SIZE)
    plaintext = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    stream = _keystream(key, nonce, len(plaintext))
    ciphertext = bytes(a ^ b for a, b in zip(plaintext, stream))
    mac = hmac.new(key, nonce + ciphertext, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(nonce + mac + ciphertext).decode("ascii")


def decrypt_json(token: str) -> dict[str, Any]:
    secret = os.environ.get(_KEY_ENV, "").strip()
    if not secret:
        raise RuntimeError(f"{_KEY_ENV} is required to decrypt this payload.")
    raw = base64.urlsafe_b64decode(token.encode("ascii"))
    nonce = raw[:_NONCE_SIZE]
    mac = raw[_NONCE_SIZE:_NONCE_SIZE + _MAC_SIZE]
    ciphertext = raw[_NONCE_SIZE + _MAC_SIZE:]
    key = _derive_key(secret)
    expected = hmac.new(key, nonce + ciphertext, hashlib.sha256).digest()
    if not hmac.compare_digest(mac, expected):
        raise ValueError("Encrypted payload integrity check failed.")
    stream = _keystream(key, nonce, len(ciphertext))
    plaintext = bytes(a ^ b for a, b in zip(ciphertext, stream))
    return json.loads(plaintext.decode("utf-8"))
