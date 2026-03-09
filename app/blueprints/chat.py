"""
Chat blueprint: AI chatbot API endpoints (SSE streaming).
"""

import json

from flask import Blueprint, Response, current_app, request, stream_with_context
from flask_login import current_user

from app.extensions import csrf, limiter
from app.services.chat_service import chat_service

chat_bp = Blueprint("chat", __name__, url_prefix="/api/chat")


@chat_bp.record_once
def _init_service(state):
    """Initialize the chat service when the blueprint is registered."""
    chat_service.init_app(state.app)


@chat_bp.route("/session", methods=["POST"])
@limiter.limit("10/minute")
@csrf.exempt
def create_session():
    """Create or resume a chat session."""
    data = request.get_json(silent=True) or {}
    session_id = data.get("session_id")
    user_id = current_user.id if current_user.is_authenticated else None

    session = chat_service.get_or_create_session(session_id, user_id)
    return {"session_id": session.id}


@chat_bp.route("/message", methods=["POST"])
@limiter.limit("20/minute")
@csrf.exempt
def send_message():
    """Accept a user message and stream the AI response via SSE."""
    data = request.get_json(silent=True) or {}
    session_id = data.get("session_id")
    message = (data.get("message") or "").strip()

    if not session_id or not message:
        return {"error": "session_id and message are required"}, 400

    if len(message) > 5000:
        return {"error": "message too long"}, 400

    user_id = current_user.id if current_user.is_authenticated else None
    session = chat_service.get_or_create_session(session_id, user_id)

    if not chat_service.available:
        return {"error": "Chat service unavailable"}, 503

    def generate():
        try:
            for chunk in chat_service.chat_stream(session, message):
                yield f"data: {json.dumps({'content': chunk})}\n\n"
            yield f"data: {json.dumps({'done': True})}\n\n"
        except Exception:
            current_app.logger.exception("Chat stream error")
            yield f"data: {json.dumps({'error': 'Erro interno. Tente novamente.'})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
