"""
Unit tests for auth token service and security flows.
"""

from app.services.auth_service import (
    generate_email_verification_token,
    generate_password_reset_token,
    verify_email_token,
    verify_password_reset_token,
)


def test_email_verification_token_roundtrip(flask_app):
    with flask_app.app_context():
        token = generate_email_verification_token("user@test.com")
        email = verify_email_token(token)
        assert email == "user@test.com"


def test_email_verification_invalid_token(flask_app):
    with flask_app.app_context():
        assert verify_email_token("totally-invalid-token") is None


def test_password_reset_token_roundtrip(flask_app):
    with flask_app.app_context():
        token = generate_password_reset_token("reset@test.com")
        email = verify_password_reset_token(token)
        assert email == "reset@test.com"


def test_password_reset_invalid_token(flask_app):
    with flask_app.app_context():
        assert verify_password_reset_token("totally-invalid-token") is None


def test_email_token_wrong_salt_fails(flask_app):
    """An email-verify token should not validate as a password-reset token."""
    with flask_app.app_context():
        token = generate_email_verification_token("cross@test.com")
        assert verify_password_reset_token(token) is None
