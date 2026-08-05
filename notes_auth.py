"""Password hashing for the Notes lock feature.

Shared by task_manager.py (the Flask app) and scripts/notes_password.py (the
CLI used to set up, change, or reset the password) so both always speak the
same hash format. Passwords are never stored in plaintext and are not
reversible -- "retrieving" the password isn't possible by design, only
verifying a guess against the stored hash or overwriting it with a new one.
"""

import hashlib
import hmac
import os

PBKDF2_ITERATIONS = 310_000  # OWASP-recommended minimum for PBKDF2-HMAC-SHA256 (2023)


def hash_password(password: str, salt: bytes | None = None) -> tuple[str, str]:
    """Return (password_hash_hex, salt_hex) for the given password."""
    if salt is None:
        salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return digest.hex(), salt.hex()


def verify_password(password: str, password_hash_hex: str, salt_hex: str) -> bool:
    """Constant-time check of a candidate password against a stored hash+salt."""
    salt = bytes.fromhex(salt_hex)
    candidate_hex, _ = hash_password(password, salt)
    return hmac.compare_digest(candidate_hex, password_hash_hex)
