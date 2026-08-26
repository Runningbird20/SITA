"""Password hashing and session-token generation. See DEF.md § Phase 14,
"Multi-user / RBAC (post-roadmap)".
"""

import hashlib
import secrets

import bcrypt


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def generate_token() -> str:
    """The raw bearer token handed to the client once, at login — never
    stored itself, only its hash (see hash_token below).
    """
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """SHA-256, not bcrypt: this token is already a high-entropy random
    value (unlike a human-chosen password), so a fast, deterministic hash
    is fine — it just needs to not be reversible from a DB leak, not resist
    brute-forcing a low-entropy secret.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
