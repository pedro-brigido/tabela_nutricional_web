"""
Auth service: token generation/verification for email verification and password reset.
Uses itsdangerous URLSafeTimedSerializer (stateless, no DB table needed).
"""

from __future__ import annotations

from flask import current_app
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer


_SALT_EMAIL_VERIFY = "email-verify"
_SALT_PASSWORD_RESET = "password-reset"


def _get_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"])


def generate_email_verification_token(email: str) -> str:
    return _get_serializer().dumps(email, salt=_SALT_EMAIL_VERIFY)


def verify_email_token(token: str, max_age: int = 86400) -> str | None:
    """Verify token, return email or None if expired/invalid. Default 24h."""
    try:
        return _get_serializer().loads(
            token, salt=_SALT_EMAIL_VERIFY, max_age=max_age
        )
    except (BadSignature, SignatureExpired):
        return None


def generate_password_reset_token(email: str) -> str:
    return _get_serializer().dumps(email, salt=_SALT_PASSWORD_RESET)


def verify_password_reset_token(token: str, max_age: int = 3600) -> str | None:
    """Verify token, return email or None if expired/invalid. Default 1h."""
    try:
        return _get_serializer().loads(
            token, salt=_SALT_PASSWORD_RESET, max_age=max_age
        )
    except (BadSignature, SignatureExpired):
        return None
