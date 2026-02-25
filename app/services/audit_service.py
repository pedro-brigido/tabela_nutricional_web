"""
Audit service: structured action logging.
"""

from __future__ import annotations

from flask import request

from app.extensions import db
from app.models.audit import AuditLog


def log_action(
    action: str,
    *,
    user_id: int | None = None,
    resource_type: str | None = None,
    resource_id: int | None = None,
    details: dict | None = None,
) -> AuditLog:
    """Record an auditable action."""
    entry = AuditLog(
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details,
        ip_address=request.remote_addr if request else None,
        user_agent=(
            str(request.user_agent)[:500] if request else None
        ),
    )
    db.session.add(entry)
    db.session.commit()
    return entry
