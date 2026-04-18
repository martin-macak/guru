"""Auth helpers."""
import hashlib

from src.pkg.services.user import UserService


class AuthError(Exception):
    pass


def hash_password(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()
