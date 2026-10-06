"""Password hashing and session cookies for Campus Customs.

Passwords are never stored. Each one is run through PBKDF2-HMAC-SHA256 with a
random per-user salt, and only the result is saved in users.password_hash.
"""

import base64
import hashlib
import hmac
import json
import os
import secrets
import time

ALGORITHM = "pbkdf2_sha256"
# OWASP's recommended minimum for PBKDF2-HMAC-SHA256.
ITERATIONS = 600_000
# Seed accounts use a 3-part hash (pbkdf2_sha256$salt$digest) with no iteration
# count stored; they were created with 120,000 iterations.
LEGACY_ITERATIONS = int(os.environ.get("LEGACY_PBKDF2_ITERATIONS", "120000"))

SESSION_COOKIE = "cc_session"
SESSION_MAX_AGE = 60 * 60 * 24 * 7  # one week
# Signs session cookies. Without SESSION_SECRET set, a random key is made at
# startup, so everyone is logged out whenever the server restarts.
_SESSION_KEY = os.environ.get("SESSION_SECRET", "").encode() or secrets.token_bytes(32)


def _pbkdf2(password: str, salt: str, iterations: int) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), iterations).hex()


def hash_password(password: str) -> str:
    """Return pbkdf2_sha256$<iterations>$<salt>$<hex digest>."""
    salt = secrets.token_hex(16)
    return f"{ALGORITHM}${ITERATIONS}${salt}${_pbkdf2(password, salt, ITERATIONS)}"


def verify_password(password: str, stored: str) -> bool:
    parts = stored.split("$")
    if len(parts) == 4:
        algorithm, iterations, salt, digest = parts
        iterations = int(iterations)
    elif len(parts) == 3:
        algorithm, salt, digest = parts
        iterations = LEGACY_ITERATIONS
    else:
        return False
    if algorithm != ALGORITHM:
        return False
    # Constant-time comparison so response timing doesn't leak how close a guess was.
    return hmac.compare_digest(_pbkdf2(password, salt, iterations), digest)


# A real hash to check against when the email doesn't exist, so a login attempt
# takes the same time whether or not the account is real.
DUMMY_HASH = hash_password(secrets.token_hex(16))


def make_session_token(user_id: int) -> str:
    payload = base64.urlsafe_b64encode(
        json.dumps({"uid": user_id, "exp": int(time.time()) + SESSION_MAX_AGE}).encode()
    ).decode()
    sig = hmac.new(_SESSION_KEY, payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def read_session_token(token: str | None) -> int | None:
    """Return the user id from a valid, unexpired token, otherwise None."""
    if not token or "." not in token:
        return None
    payload, sig = token.rsplit(".", 1)
    expected = hmac.new(_SESSION_KEY, payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        data = json.loads(base64.urlsafe_b64decode(payload))
    except ValueError:
        return None
    if data.get("exp", 0) < time.time():
        return None
    return data.get("uid")


class LoginLimiter:
    """Blocks an email after too many failed logins in a short window."""

    def __init__(self, max_failures: int = 5, window_seconds: int = 15 * 60):
        self.max_failures = max_failures
        self.window = window_seconds
        self._failures: dict[str, list[float]] = {}

    def _recent(self, key: str) -> list[float]:
        cutoff = time.time() - self.window
        recent = [t for t in self._failures.get(key, []) if t > cutoff]
        self._failures[key] = recent
        return recent

    def is_blocked(self, key: str) -> bool:
        return len(self._recent(key)) >= self.max_failures

    def record_failure(self, key: str) -> None:
        self._recent(key).append(time.time())

    def reset(self, key: str) -> None:
        self._failures.pop(key, None)
