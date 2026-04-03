from __future__ import annotations

import hashlib
import hmac
import os


PBKDF2_ALGORITHM = "sha256"
PBKDF2_ITERATIONS = 200_000
SALT_BYTES = 16
REMEMBER_TOKEN_BYTES = 32
REMEMBER_SELECTOR_BYTES = 16


def hash_password(password: str) -> str:
    password_text = str(password)
    salt = os.urandom(SALT_BYTES)
    digest = hashlib.pbkdf2_hmac(
        PBKDF2_ALGORITHM,
        password_text.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS,
    )
    return f"pbkdf2_{PBKDF2_ALGORITHM}${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, iterations_text, salt_hex, digest_hex = str(stored_hash).split("$", 3)
    except ValueError:
        return False

    if algorithm != f"pbkdf2_{PBKDF2_ALGORITHM}":
        return False

    try:
        iterations = int(iterations_text)
        salt = bytes.fromhex(salt_hex)
        expected_digest = bytes.fromhex(digest_hex)
    except (ValueError, TypeError):
        return False

    calculated_digest = hashlib.pbkdf2_hmac(
        PBKDF2_ALGORITHM,
        str(password).encode("utf-8"),
        salt,
        iterations,
    )
    return hmac.compare_digest(calculated_digest, expected_digest)


def generate_remember_selector() -> str:
    return os.urandom(REMEMBER_SELECTOR_BYTES).hex()


def generate_remember_secret() -> str:
    return os.urandom(REMEMBER_TOKEN_BYTES).hex()


def hash_remember_secret(secret: str) -> str:
    return hashlib.sha256(str(secret).encode("utf-8")).hexdigest()


def verify_remember_secret(secret: str, stored_hash: str) -> bool:
    calculated_hash = hash_remember_secret(secret)
    return hmac.compare_digest(calculated_hash, str(stored_hash))
