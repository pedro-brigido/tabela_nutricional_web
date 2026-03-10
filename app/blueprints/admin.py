"""
Admin blueprint: user management, plan assignment, audit logs, tickets.
"""

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app.decorators import require_role
from app.extensions import db
from app.models.audit import AuditLog
from app.models.plan import Plan, Subscription, UsageRecord
from app.models.support import SupportTicket
from app.models.user import User
from app.services.audit_service import log_action
from app.services.chatbot_service import chatbot_metrics
from app.services.plan_service import (
    assign_plan,
    get_user_plan,
    get_user_subscription,
)
from app.services.usage_service import get_usage

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@admin_bp.route("/")
@require_role("admin")
def dashboard():
    total_users = User.query.count()
    total_tables_month = db.session.query(
        db.func.sum(UsageRecord.tables_created)
    ).scalar() or 0
    plan_dist = (
        db.session.query(Plan.name, db.func.count(Subscription.id))
        .join(Subscription, Subscription.plan_id == Plan.id)
        .filter(Subscription.status == "active")
        .group_by(Plan.name)
        .all()
    )
    open_tickets = SupportTicket.query.filter_by(status="open").count()
    chatbot_summary = chatbot_metrics()

    return render_template(
        "admin/dashboard.html",
        total_users=total_users,
        total_tables_month=total_tables_month,
        plan_dist=plan_dist,
        open_tickets=open_tickets,
        total_chatbot_conversations=chatbot_summary["total_conversations"],
    )


@admin_bp.route("/users")
@require_role("admin")
def user_list():
    page = request.args.get("page", 1, type=int)
    q = request.args.get("q", "").strip()
    query = User.query
    if q:
        query = query.filter(
            User.email.ilike(f"%{q}%") | User.name.ilike(f"%{q}%")
        )
    pagination = query.order_by(User.created_at.desc()).paginate(
        page=page, per_page=20, error_out=False
    )
    return render_template(
        "admin/user_list.html", pagination=pagination, q=q
    )


@admin_bp.route("/users/<int:user_id>")
@require_role("admin")
def user_detail(user_id):
    user = db.session.get(User, user_id)
    if not user:
        flash("Usuário não encontrado.", "error")
        return redirect(url_for("admin.user_list"))

    plan = get_user_plan(user_id)
    usage = get_usage(user_id)
    plans = Plan.query.filter_by(is_active=True).order_by(Plan.display_order).all()
    logs = (
        AuditLog.query.filter_by(user_id=user_id)
        .order_by(AuditLog.created_at.desc())
        .limit(20)
        .all()
    )

    return render_template(
        "admin/user_detail.html",
        user=user,
        plan=plan,
        subscription=get_user_subscription(user_id),
        usage=usage,
        plans=plans,
        logs=logs,
    )


@admin_bp.route("/users/<int:user_id>/set-plan", methods=["POST"])
@require_role("admin")
def set_plan(user_id):
    plan_slug = request.form.get("plan_slug", "")
    try:
        assign_plan(user_id, plan_slug, assigned_by="admin")
        log_action(
            "plan.change",
            user_id=user_id,
            details={"new_plan": plan_slug, "admin_id": current_user.id},
        )
        flash(f"Plano alterado para {plan_slug}.", "success")
    except ValueError as e:
        flash(str(e), "error")
    return redirect(url_for("admin.user_detail", user_id=user_id))


@admin_bp.route("/users/<int:user_id>/adjust-quota", methods=["POST"])
@require_role("admin")
def adjust_quota(user_id):
    tables = request.form.get("tables_created", type=int)
    if tables is not None and tables >= 0:
        usage = get_usage(user_id)
        usage.tables_created = tables
        db.session.commit()
        log_action(
            "quota.adjust",
            user_id=user_id,
            details={"new_tables_created": tables, "admin_id": current_user.id},
        )
        flash("Quota ajustada.", "success")
    return redirect(url_for("admin.user_detail", user_id=user_id))


@admin_bp.route("/users/<int:user_id>/toggle-active", methods=["POST"])
@require_role("admin")
def toggle_active(user_id):
    user = db.session.get(User, user_id)
    if user:
        user.is_active = not user.is_active
        db.session.commit()
        log_action(
            "user.toggle_active",
            user_id=user_id,
            details={"is_active": user.is_active, "admin_id": current_user.id},
        )
        flash(
            f"Usuário {'ativado' if user.is_active else 'desativado'}.",
            "success",
        )
    return redirect(url_for("admin.user_detail", user_id=user_id))


@admin_bp.route("/logs")
@require_role("admin")
def logs():
    page = request.args.get("page", 1, type=int)
    action_filter = request.args.get("action", "").strip()
    query = AuditLog.query
    if action_filter:
        query = query.filter(AuditLog.action.ilike(f"%{action_filter}%"))
    pagination = query.order_by(AuditLog.created_at.desc()).paginate(
        page=page, per_page=50, error_out=False
    )
    return render_template(
        "admin/logs.html", pagination=pagination, action_filter=action_filter
    )


@admin_bp.route("/tickets")
@require_role("admin")
def tickets():
    page = request.args.get("page", 1, type=int)
    status_filter = request.args.get("status", "").strip()
    query = SupportTicket.query
    if status_filter:
        query = query.filter_by(status=status_filter)
    pagination = query.order_by(SupportTicket.created_at.desc()).paginate(
        page=page, per_page=20, error_out=False
    )
    return render_template(
        "admin/tickets.html", pagination=pagination, status_filter=status_filter
    )


@admin_bp.route("/chatbot")
@require_role("admin")
def chatbot():
    metrics = chatbot_metrics()
    return render_template("admin/chatbot.html", metrics=metrics)


@admin_bp.route("/tickets/<int:ticket_id>/update", methods=["POST"])
@require_role("admin")
def update_ticket(ticket_id):
    ticket = db.session.get(SupportTicket, ticket_id)
    if not ticket:
        flash("Ticket não encontrado.", "error")
        return redirect(url_for("admin.tickets"))

    new_status = request.form.get("status", ticket.status)
    admin_notes = request.form.get("admin_notes", "")

    ticket.status = new_status
    if admin_notes:
        ticket.admin_notes = admin_notes
    db.session.commit()

    log_action(
        "ticket.update",
        user_id=current_user.id,
        resource_type="support_ticket",
        resource_id=ticket_id,
        details={"new_status": new_status},
    )

    flash("Ticket atualizado.", "success")
    return redirect(url_for("admin.tickets"))
