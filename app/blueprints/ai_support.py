"""
AI chatbot support blueprint.
"""

from __future__ import annotations

import secrets
import json

from flask import Blueprint, current_app, jsonify, make_response, request, Response, stream_with_context
from flask_login import current_user

from app.extensions import limiter
from app.services.chatbot_service import (
    ChatbotError,
    ChatbotModerationError,
    ChatbotOwnershipError,
    build_initial_messages,
    chatbot_enabled,
    create_message,
    get_conversation_for_actor,
    get_or_create_conversation,
    hash_anon_token,
    process_user_message,
    record_feedback,
    serialize_conversation,
    stream_user_message,
)

ai_support_bp = Blueprint("ai_support", __name__, url_prefix="")


def _actor_limit(guest_limit: str, auth_limit: str):
    def _limit():
        return auth_limit if current_user.is_authenticated else guest_limit

    return _limit


def _anon_cookie_name() -> str:
    return current_app.config.get("CHATBOT_COOKIE_NAME", "terracota_chat_anon")


def _get_or_issue_anon_token() -> tuple[str, bool]:
    if current_user.is_authenticated:
        return "", False
    token = request.cookies.get(_anon_cookie_name(), "").strip()
    if token:
        return token, False
    return secrets.token_urlsafe(24), True


def _conversation_actor():
    token, created = _get_or_issue_anon_token()
    return {
        "user_id": current_user.id if current_user.is_authenticated else None,
        "anon_token": token,
        "anon_token_hash": hash_anon_token(token) if token else None,
        "cookie_created": created,
    }


def _set_anon_cookie(response, token: str) -> None:
    if not token or current_user.is_authenticated:
        return
    response.set_cookie(
        _anon_cookie_name(),
        token,
        max_age=60 * 60 * 24 * int(current_app.config["CHATBOT_ANON_RETENTION_DAYS"]),
        httponly=True,
        secure=bool(current_app.config.get("SESSION_COOKIE_SECURE", False)),
        samesite="Lax",
    )


def _feature_disabled():
    return jsonify({"error": "Assistente IA indisponível.", "enabled": False}), 404


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@ai_support_bp.post("/api/chat/session")
@limiter.limit(_actor_limit("10 per 15 minutes", "30 per 15 minutes"))
def chatbot_session():
    if not chatbot_enabled():
        return _feature_disabled()

    payload = request.get_json(silent=True) or {}
    actor = _conversation_actor()
    conversation = get_or_create_conversation(
        user_id=actor["user_id"],
        anon_token_hash=actor["anon_token_hash"],
        source_page=(payload.get("source_page") or "landing-faq"),
        locale=(payload.get("locale") or "pt-BR"),
    )
    if conversation.messages.count() == 0:
        for item in build_initial_messages():
            create_message(
                conversation=conversation,
                role=item["role"],
                content=item["content"],
                citations=item.get("citations", []),
            )

    response = make_response(
        jsonify(
            {
                "enabled": True,
                **serialize_conversation(conversation),
            }
        )
    )
    if actor["cookie_created"]:
        _set_anon_cookie(response, actor["anon_token"])
    return response


@ai_support_bp.post("/api/chat/message")
@limiter.limit(_actor_limit("15 per 15 minutes", "45 per 15 minutes"))
def chatbot_message():
    if not chatbot_enabled():
        return _feature_disabled()

    payload = request.get_json(silent=True) or {}
    conversation_id = (payload.get("conversation_id") or "").strip()
    actor = _conversation_actor()
    try:
        conversation = get_conversation_for_actor(
            conversation_id,
            user_id=actor["user_id"],
            anon_token_hash=actor["anon_token_hash"],
        )
    except ChatbotOwnershipError as exc:
        return jsonify({"error": str(exc)}), 403
    if not conversation:
        return jsonify({"error": "Conversa não encontrada."}), 404

    try:
        data = process_user_message(
            conversation=conversation,
            message=payload.get("message") or "",
            page_context=payload.get("page_context"),
            locale=payload.get("locale"),
        )
    except ChatbotModerationError as exc:
        return jsonify(
            {
                "error": str(exc),
                "needs_human": True,
            }
        ), 422
    except ChatbotOwnershipError as exc:
        return jsonify({"error": str(exc)}), 403
    except ChatbotError as exc:
        return jsonify({"error": str(exc)}), 400

    response = make_response(jsonify(data))
    if actor["cookie_created"]:
        _set_anon_cookie(response, actor["anon_token"])
    return response


@ai_support_bp.post("/api/chat/message/stream")
@limiter.limit(_actor_limit("15 per 15 minutes", "45 per 15 minutes"))
def chatbot_message_stream():
    if not chatbot_enabled():
        return _feature_disabled()

    payload = request.get_json(silent=True) or {}
    conversation_id = (payload.get("conversation_id") or "").strip()
    actor = _conversation_actor()
    try:
        conversation = get_conversation_for_actor(
            conversation_id,
            user_id=actor["user_id"],
            anon_token_hash=actor["anon_token_hash"],
        )
    except ChatbotOwnershipError as exc:
        return jsonify({"error": str(exc)}), 403
    if not conversation:
        return jsonify({"error": "Conversa não encontrada."}), 404

    @stream_with_context
    def generate():
        try:
            yield _sse("start", {"conversation_id": conversation.id})
            for event_name, event_payload in stream_user_message(
                conversation=conversation,
                message=payload.get("message") or "",
                page_context=payload.get("page_context"),
                locale=payload.get("locale"),
            ):
                yield _sse(event_name, event_payload)
        except ChatbotModerationError as exc:
            yield _sse("error", {"error": str(exc), "needs_human": True})
        except ChatbotOwnershipError as exc:
            yield _sse("error", {"error": str(exc)})
        except ChatbotError as exc:
            yield _sse("error", {"error": str(exc)})
        except Exception:
            current_app.logger.exception("Unexpected error in chatbot streaming response.")
            yield _sse(
                "error",
                {
                    "error": "Assistente indisponível no momento. Use o contato por e-mail.",
                    "needs_human": True,
                },
            )

    response = Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
    if actor["cookie_created"]:
        _set_anon_cookie(response, actor["anon_token"])
    return response


@ai_support_bp.get("/api/chat/history/<conversation_id>")
@limiter.limit(_actor_limit("30 per hour", "120 per hour"))
def chatbot_history(conversation_id: str):
    if not chatbot_enabled():
        return _feature_disabled()

    actor = _conversation_actor()
    try:
        conversation = get_conversation_for_actor(
            conversation_id,
            user_id=actor["user_id"],
            anon_token_hash=actor["anon_token_hash"],
        )
    except ChatbotOwnershipError as exc:
        return jsonify({"error": str(exc)}), 403

    if not conversation:
        return jsonify({"error": "Conversa não encontrada."}), 404
    response = make_response(jsonify(serialize_conversation(conversation)))
    if actor["cookie_created"]:
        _set_anon_cookie(response, actor["anon_token"])
    return response


@ai_support_bp.post("/api/chat/feedback")
@limiter.limit(_actor_limit("20 per hour", "60 per hour"))
def chatbot_feedback():
    if not chatbot_enabled():
        return _feature_disabled()

    payload = request.get_json(silent=True) or {}
    actor = _conversation_actor()
    try:
        conversation = get_conversation_for_actor(
            (payload.get("conversation_id") or "").strip(),
            user_id=actor["user_id"],
            anon_token_hash=actor["anon_token_hash"],
        )
    except ChatbotOwnershipError as exc:
        return jsonify({"error": str(exc)}), 403

    if not conversation:
        return jsonify({"error": "Conversa não encontrada."}), 404

    rating = (payload.get("rating") or "").strip().lower()
    if rating not in {"up", "down"}:
        return jsonify({"error": "Feedback inválido."}), 400

    try:
        feedback = record_feedback(
            conversation=conversation,
            message_id=int(payload.get("message_id") or 0),
            rating=rating,
            note=(payload.get("note") or ""),
        )
    except ChatbotError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"ok": True, "feedback_id": feedback.id})
