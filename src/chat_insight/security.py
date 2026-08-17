from __future__ import annotations

import hashlib
import hmac
import secrets

from cryptography.fernet import Fernet, InvalidToken
from pwdlib import PasswordHash

_passwords = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return _passwords.hash(password)


def verify_password(password: str, encoded: str) -> bool:
    return _passwords.verify(password, encoded)


def token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def constant_time_equal(left: str | None, right: str | None) -> bool:
    return bool(left and right and hmac.compare_digest(left, right))


def mask_secret(value: str | None) -> str | None:
    if not value:
        return None
    if len(value) <= 8:
        return "********"
    return f"{value[:4]}…{value[-4:]}"


class SecretBox:
    def __init__(self, key: str) -> None:
        self._fernet = Fernet(key.encode())

    def encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode()).decode()

    def decrypt(self, value: str | None) -> str | None:
        if not value:
            return None
        try:
            return self._fernet.decrypt(value.encode()).decode()
        except InvalidToken as exc:
            raise RuntimeError("Stored secret cannot be decrypted with the configured key") from exc
