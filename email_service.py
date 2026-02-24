"""
Email utilities for transactional messages.
"""

from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage

from flask import current_app


def _smtp_settings() -> dict:
    return {
        "host": os.environ.get("SMTP_HOST", "").strip(),
        "port": int(os.environ.get("SMTP_PORT", "587")),
        "user": os.environ.get("SMTP_USER", "").strip(),
        "password": os.environ.get("SMTP_PASSWORD", ""),
        "use_tls": os.environ.get("SMTP_USE_TLS", "true").lower() in ("1", "true", "yes", "on"),
        "email_from": os.environ.get("EMAIL_FROM", "").strip(),
    }


def _build_message(*, subject: str, body: str, to_email: str, from_email: str) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_email
    msg["To"] = to_email
    msg.set_content(body)
    return msg


def send_email(*, subject: str, body: str, to_email: str) -> bool:
    cfg = _smtp_settings()
    if not cfg["host"] or not cfg["user"] or not cfg["password"] or not cfg["email_from"]:
        current_app.logger.warning("SMTP não configurado completamente. E-mail não enviado para %s.", to_email)
        return False

    msg = _build_message(subject=subject, body=body, to_email=to_email, from_email=cfg["email_from"])

    try:
        with smtplib.SMTP(cfg["host"], cfg["port"], timeout=15) as server:
            if cfg["use_tls"]:
                server.starttls()
            server.login(cfg["user"], cfg["password"])
            server.send_message(msg)
        return True
    except Exception:
        current_app.logger.exception("Falha ao enviar e-mail para %s.", to_email)
        return False


def send_welcome_email(*, user_name: str, user_email: str) -> bool:
    subject = "Bem-vindo(a) à Terracota | Calculadora Nutricional"
    body = (
        f"Olá, {user_name}!\n\n"
        "Sua conta foi criada com sucesso na Terracota | Calculadora Nutricional.\n"
        "Agora você já pode acessar a plataforma e gerar suas tabelas nutricionais.\n\n"
        "Se precisar de ajuda, responda este e-mail.\n\n"
        "Atenciosamente,\n"
        "Equipe Terracota"
    )
    return send_email(subject=subject, body=body, to_email=user_email)


def send_newsletter_notification(*, subscriber_email: str, notify_email: str) -> bool:
    subject = "Nova submissão de newsletter"
    body = (
        "Uma nova submissão de newsletter foi recebida.\n\n"
        f"E-mail informado: {subscriber_email}\n"
    )
    return send_email(subject=subject, body=body, to_email=notify_email)
