"""Password hashing and session-token primitives.

No third-party crypto dependency is added: ``hashlib.scrypt`` is in the standard
library, memory-hard, and its parameters can be encoded alongside the hash so a
future upgrade does not need a migration. Session tokens are opaque random
values whose SHA-256 hash is what the database stores, so a database leak cannot
be replayed.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

# scrypt cost parameters. n=2**14 with r=8/p=1 is the commonly reviewed baseline
# for interactive logins (roughly tens of milliseconds, ~16 MiB).
SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
SALT_BYTES = 16
KEY_BYTES = 32


def hash_password(password: str) -> str:
    """Return ``scrypt$n$r$p$<salt-hex>$<hash-hex>`` for storage."""
    salt = secrets.token_bytes(SALT_BYTES)
    derived = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=KEY_BYTES,
    )
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${salt.hex()}${derived.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    """Constant-time comparison; a malformed hash verifies as False, never raises."""
    try:
        scheme, n, r, p, salt_hex, hash_hex = encoded.split("$")
        if scheme != "scrypt":
            return False
        derived = hashlib.scrypt(
            password.encode("utf-8"),
            salt=bytes.fromhex(salt_hex),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(bytes.fromhex(hash_hex)),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(derived.hex(), hash_hex)


def new_session_token() -> str:
    """An opaque bearer value; only its hash is persisted."""
    return secrets.token_urlsafe(32)


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def hash_client_address(address: str) -> str:
    """Store a coarse, non-reversible marker instead of a raw client IP."""
    return hashlib.sha256(address.encode("utf-8")).hexdigest()[:32]
