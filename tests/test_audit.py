"""
Tests for audit logging.
"""

from app.extensions import db
from app.models.audit import AuditLog
from app.services.audit_service import log_action


def test_log_action_creates_record(flask_app):
    with flask_app.app_context():
        entry = log_action(
            "test.action",
            user_id=None,
            resource_type="test",
            details={"key": "value"},
        )
        assert entry.id is not None
        assert entry.action == "test.action"

        found = db.session.get(AuditLog, entry.id)
        assert found is not None
        assert found.details == {"key": "value"}
