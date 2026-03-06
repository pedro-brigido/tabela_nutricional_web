"""
Support blueprint: help center, contact form, tickets.
"""

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.extensions import db, limiter
from app.models.support import SupportTicket
from app.services.email_service import send_email

support_bp = Blueprint("support", __name__, url_prefix="")


@support_bp.route("/help")
def help_page():
    return redirect(url_for("main.index") + "#ajuda")


@support_bp.route("/contact", methods=["GET", "POST"])
@limiter.limit("5/hour")
def contact():
    allowed_categories = {"other", "billing", "bug", "feature", "account"}

    def _prefill_from_args():
        category = (request.args.get("category") or "other")[:50]
        if category not in allowed_categories:
            category = "other"
        subject = (request.args.get("subject") or "").strip()[:255]
        message = (request.args.get("message") or "").strip()[:5000]
        plan = (request.args.get("plan") or "").strip()[:50]
        source = (request.args.get("source") or "").strip()[:50]

        if plan and not subject:
            subject = f"Plano: {plan}"
        if (plan or source) and not message:
            parts = []
            if source:
                parts.append(f"Origem: {source}")
            if plan:
                parts.append(f"Plano: {plan}")
            if parts:
                message = "\n".join(parts) + "\n\n"
        return {
            "category": category,
            "subject": subject,
            "message": message,
        }

    if request.method == "POST":
        name = (request.form.get("name") or "").strip()[:255]
        email = (request.form.get("email") or "").strip().lower()[:255]
        category = (request.form.get("category") or "other")[:50]
        subject = (request.form.get("subject") or "").strip()[:255]
        message = (request.form.get("message") or "").strip()[:5000]

        if category not in allowed_categories:
            category = "other"

        if not name or not email or not message:
            flash("Preencha todos os campos obrigatórios.", "error")
            return redirect(url_for("main.index") + "#contato")

        if current_user.is_authenticated:
            ticket = SupportTicket(
                user_id=current_user.id,
                subject=subject or "Contato",
                category=category,
                message=message,
            )
            db.session.add(ticket)
            db.session.commit()

        send_email(
            subject=f"[Contato] {subject or 'Mensagem'} — {name}",
            body=f"De: {name} ({email})\nCategoria: {category}\n\n{message}",
            to_email="comercial@terracotabpo.com",
        )

        flash("Mensagem enviada! Responderemos em breve.", "success")
        return redirect(url_for("main.index") + "#contato")

    return redirect(url_for("main.index") + "#contato")


@support_bp.route("/support/tickets")
@login_required
def ticket_list():
    tickets = (
        SupportTicket.query.filter_by(user_id=current_user.id)
        .order_by(SupportTicket.created_at.desc())
        .all()
    )
    return render_template("support/ticket_list.html", tickets=tickets)


@support_bp.route("/support/tickets", methods=["POST"])
@login_required
@limiter.limit("5/hour")
def create_ticket():
    subject = (request.form.get("subject") or "").strip()[:255]
    category = (request.form.get("category") or "other")[:50]
    message = (request.form.get("message") or "").strip()[:5000]

    if not subject or not message:
        flash("Preencha assunto e mensagem.", "error")
        return redirect(url_for("support.ticket_list"))

    ticket = SupportTicket(
        user_id=current_user.id,
        subject=subject,
        category=category,
        message=message,
    )
    db.session.add(ticket)
    db.session.commit()
    flash("Ticket criado com sucesso.", "success")
    return redirect(url_for("support.ticket_list"))
