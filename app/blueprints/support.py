"""
Support blueprint: legacy public redirects, contact intake, tickets.
"""

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.extensions import db, limiter
from app.models.support import SupportTicket
from app.services.email_service import send_email

support_bp = Blueprint("support", __name__, url_prefix="")
ALLOWED_CONTACT_CATEGORIES = {"other", "billing", "bug", "feature", "account"}


def _request_wants_json() -> bool:
    return bool(
        request.is_json
        or request.headers.get("X-Requested-With") == "fetch"
        or request.accept_mimetypes.best == "application/json"
    )


def compose_contact_message(
    *,
    message: str,
    plan: str = "",
    source: str = "",
    conversation_id: str = "",
) -> str:
    final_message = (message or "").strip()[:5000]
    prefix_lines = []
    if source and f"Origem: {source}" not in final_message:
        prefix_lines.append(f"Origem: {source}")
    if plan and f"Plano: {plan}" not in final_message:
        prefix_lines.append(f"Plano: {plan}")
    if conversation_id and f"Conversation ID: {conversation_id}" not in final_message:
        prefix_lines.append(f"Conversation ID: {conversation_id}")
    if prefix_lines:
        prefix = "\n".join(prefix_lines)
        final_message = f"{prefix}\n\n{final_message}".strip()
    return final_message


def build_contact_prefill(source_data) -> dict[str, str]:
    category = (source_data.get("category") or "other")[:50]
    if category not in ALLOWED_CONTACT_CATEGORIES:
        category = "other"

    subject = (source_data.get("subject") or "").strip()[:255]
    message = (source_data.get("message") or "").strip()[:5000]
    plan = (source_data.get("plan") or "").strip()[:50]
    source = (source_data.get("source") or "").strip()[:50]
    conversation_id = (source_data.get("conversation_id") or "").strip()[:64]

    if plan and not subject:
        subject = f"Plano: {plan}"

    message = compose_contact_message(
        message=message,
        plan=plan if plan or not message else "",
        source=source if source or not message else "",
        conversation_id=conversation_id,
    )

    return {
        "category": category,
        "subject": subject,
        "message": message,
        "plan": plan,
        "source": source,
        "conversation_id": conversation_id,
    }


def _landing_anchor_url(anchor: str, params: dict[str, str] | None = None) -> str:
    query = {key: value for key, value in (params or {}).items() if value}
    return url_for("main.index", _anchor=anchor, **query)


@support_bp.route("/help")
def help_page():
    return redirect(url_for("main.index", _anchor="faq"), code=301)


@support_bp.route("/contact", methods=["GET", "POST"])
@limiter.limit("5/hour")
def contact():
    if request.method == "GET":
        query_params = request.args.to_dict(flat=True)
        return redirect(_landing_anchor_url("contato", query_params), code=301)

    incoming = request.get_json(silent=True) or {}
    source_data = incoming if request.is_json else request.form
    prefill = build_contact_prefill(source_data)

    name = (source_data.get("name") or "").strip()[:255]
    email = (source_data.get("email") or "").strip().lower()[:255]
    category = prefill["category"]
    subject = prefill["subject"]
    message = compose_contact_message(
        message=(source_data.get("message") or "").strip()[:5000],
        plan=(source_data.get("plan") or "").strip()[:50],
        source=(source_data.get("source") or "").strip()[:50],
        conversation_id=(source_data.get("conversation_id") or "").strip()[:64],
    )

    if not name or not email or not message:
        error_payload = {
            "error": "Preencha todos os campos obrigatórios.",
            "fields": {
                "name": bool(name),
                "email": bool(email),
                "message": bool(message),
            },
        }
        if _request_wants_json():
            return jsonify(error_payload), 400
        flash("Preencha todos os campos obrigatórios.", "error")
        return redirect(_landing_anchor_url("contato", prefill))

    if current_user.is_authenticated:
        ticket = SupportTicket(
            user_id=current_user.id,
            subject=subject or "Contato",
            category=category,
            message=message,
        )
        db.session.add(ticket)
        db.session.commit()

    email_sent = send_email(
        subject=f"[Contato] {subject or 'Mensagem'} — {name}",
        body=f"De: {name} ({email})\nCategoria: {category}\n\n{message}",
        to_email="comercial@terracotabpo.com",
    )

    if _request_wants_json():
        if not email_sent and not current_user.is_authenticated:
            return (
                jsonify(
                    {
                        "error": "Não foi possível enviar sua mensagem agora. Tente novamente em alguns minutos.",
                    }
                ),
                503,
            )
        return jsonify(
            {
                "ok": True,
                "message": "Mensagem enviada! Responderemos em breve.",
            }
        )

    flash("Mensagem enviada! Responderemos em breve.", "success")
    return redirect(url_for("main.index", _anchor="contato"))


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
