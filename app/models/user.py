"""
User model for authentication.
Supports email/password (argon2id) and OAuth (e.g. Google).
Maintains backward compatibility with Werkzeug PBKDF2 hashes.
"""

from datetime import datetime, timezone

from flask_login import UserMixin
from werkzeug.security import check_password_hash

from app.extensions import db

try:
    from argon2 import PasswordHasher
    from argon2.exceptions import VerifyMismatchError, VerificationError

    _ph = PasswordHasher()
    _HAS_ARGON2 = True
except ImportError:
    _HAS_ARGON2 = False


def _hash_password(password: str) -> str:
    if _HAS_ARGON2:
        return _ph.hash(password)
    from werkzeug.security import generate_password_hash

    return generate_password_hash(password)


def _verify_password(stored_hash: str, password: str) -> tuple[bool, bool]:
    """Return (is_valid, needs_rehash)."""
    if _HAS_ARGON2 and stored_hash.startswith("$argon2"):
        try:
            _ph.verify(stored_hash, password)
            needs_rehash = _ph.check_needs_rehash(stored_hash)
            return True, needs_rehash
        except (VerifyMismatchError, VerificationError):
            return False, False

    # Fallback: Werkzeug PBKDF2 hashes
    valid = check_password_hash(stored_hash, password)
    return valid, valid  # if valid, flag for rehash to argon2


class User(db.Model, UserMixin):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    name = db.Column(db.String(255), nullable=False)
    password_hash = db.Column(db.String(255), nullable=True)
    oauth_provider = db.Column(db.String(50), nullable=True)
    oauth_id = db.Column(db.String(255), nullable=True)
    stripe_customer_id = db.Column(
        db.String(255), unique=True, nullable=True, index=True
    )
    created_at = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc)
    )
    is_active = db.Column(db.Boolean, default=True)

    is_admin = db.Column(db.Boolean, default=False)
    email_verified = db.Column(db.Boolean, default=False)
    email_verified_at = db.Column(db.DateTime, nullable=True)
    last_login_at = db.Column(db.DateTime, nullable=True)
    login_count = db.Column(db.Integer, default=0)
    deleted_at = db.Column(db.DateTime, nullable=True)

    def set_password(self, password: str) -> None:
        self.password_hash = _hash_password(password)

    def check_password(self, password: str) -> bool:
        if not self.password_hash:
            return False
        valid, needs_rehash = _verify_password(self.password_hash, password)
        if valid and needs_rehash:
            self.password_hash = _hash_password(password)
        return valid

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None
