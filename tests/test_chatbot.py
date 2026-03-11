from app.models.chatbot import ChatbotConversation, ChatbotFeedback
from app.models.user import User


def _enable_chatbot(flask_app):
    flask_app.config["CHATBOT_ENABLED"] = True
    flask_app.config["OPENAI_API_KEY"] = ""


def test_chatbot_session_returns_404_when_disabled(client, flask_app):
    flask_app.config["CHATBOT_ENABLED"] = False

    response = client.post("/api/chat/session", json={"source_page": "landing-faq"})

    assert response.status_code == 404
    assert response.json["enabled"] is False


def test_chatbot_session_sets_cookie_and_returns_welcome_message(client, flask_app):
    _enable_chatbot(flask_app)

    response = client.post("/api/chat/session", json={"source_page": "landing-faq"})

    assert response.status_code == 200
    assert response.json["enabled"] is True
    assert response.json["conversation_id"]
    assert response.json["messages"][0]["role"] == "assistant"
    assert "Terracota" in response.json["messages"][0]["content"]
    assert "terracota_chat_anon=" in response.headers.get("Set-Cookie", "")


def test_chatbot_history_reuses_anonymous_conversation_cookie(client, flask_app):
    _enable_chatbot(flask_app)
    session_response = client.post("/api/chat/session", json={"source_page": "landing-faq"})
    conversation_id = session_response.json["conversation_id"]

    history_response = client.get(f"/api/chat/history/{conversation_id}")

    assert history_response.status_code == 200
    assert history_response.json["conversation_id"] == conversation_id
    assert history_response.json["messages"][0]["role"] == "assistant"


def test_chatbot_feedback_is_persisted_for_existing_message(client, flask_app, db_session):
    _enable_chatbot(flask_app)
    session_response = client.post("/api/chat/session", json={"source_page": "landing-faq"})
    conversation_id = session_response.json["conversation_id"]
    message_id = session_response.json["messages"][0]["id"]

    response = client.post(
        "/api/chat/feedback",
        json={
            "conversation_id": conversation_id,
            "message_id": message_id,
            "rating": "up",
        },
    )

    assert response.status_code == 200
    assert response.json["ok"] is True
    assert db_session.query(ChatbotFeedback).count() == 1


def test_chatbot_feedback_rejects_message_from_another_conversation(client, flask_app):
    _enable_chatbot(flask_app)
    first = client.post("/api/chat/session", json={"source_page": "landing-faq"}).json
    second_client = flask_app.test_client()
    second = second_client.post("/api/chat/session", json={"source_page": "landing-faq"}).json

    response = second_client.post(
        "/api/chat/feedback",
        json={
            "conversation_id": second["conversation_id"],
            "message_id": first["messages"][0]["id"],
            "rating": "down",
        },
    )

    assert response.status_code == 400
    assert "Mensagem inválida" in response.json["error"]


def test_chatbot_message_returns_safe_handoff_when_openai_is_unavailable(client, flask_app):
    _enable_chatbot(flask_app)
    session_response = client.post("/api/chat/session", json={"source_page": "landing-faq"})
    conversation_id = session_response.json["conversation_id"]

    response = client.post(
        "/api/chat/message",
        json={
            "conversation_id": conversation_id,
            "message": "Quais sao os planos e como funciona o PDF?",
            "page_context": "landing-faq",
            "locale": "pt-BR",
        },
    )

    assert response.status_code == 200
    assert response.json["conversation_id"] == conversation_id
    assert response.json["needs_human"] is True
    assert response.json["handoff_url"]
    assert response.json["message_id"] > 0


def test_chatbot_stream_endpoint_returns_sse_done_event(client, flask_app):
    _enable_chatbot(flask_app)
    session_response = client.post("/api/chat/session", json={"source_page": "landing-faq"})
    conversation_id = session_response.json["conversation_id"]

    response = client.post(
        "/api/chat/message/stream",
        json={
            "conversation_id": conversation_id,
            "message": "Qual plano cobre exportacao em PDF?",
            "page_context": "landing-faq",
            "locale": "pt-BR",
        },
    )

    text = response.data.decode("utf-8")
    assert response.status_code == 200
    assert response.mimetype == "text/event-stream"
    assert "event: start" in text
    assert "event: done" in text
    assert '"needs_human": true' in text or '"needs_human":true' in text


def test_chatbot_stream_endpoint_emits_replace_event(client, flask_app, monkeypatch):
    _enable_chatbot(flask_app)
    session_response = client.post("/api/chat/session", json={"source_page": "landing-faq"})
    conversation_id = session_response.json["conversation_id"]

    def _fake_stream_user_message(*, conversation, message, page_context=None, locale=None):
        yield ("replace", {"message": "Refazendo com modelo alternativo..."})
        yield ("delta", {"delta": "Resposta ajustada."})
        yield (
            "done",
            {
                "conversation_id": conversation.id,
                "message_id": 999,
                "answer": "Resposta ajustada.",
                "citations": [],
                "confidence": "medium",
                "needs_human": False,
                "suggested_actions": ["Ver central de ajuda completa"],
            },
        )

    monkeypatch.setattr(
        "app.blueprints.ai_support.stream_user_message",
        _fake_stream_user_message,
    )

    response = client.post(
        "/api/chat/message/stream",
        json={
            "conversation_id": conversation_id,
            "message": "Teste de fallback no streaming.",
            "page_context": "landing-faq",
            "locale": "pt-BR",
        },
    )

    text = response.data.decode("utf-8")
    assert response.status_code == 200
    assert "event: replace" in text
    assert "Refazendo com modelo alternativo" in text


def test_moderate_message_fails_open_when_provider_errors(flask_app, monkeypatch):
    import app.services.chatbot_service as chatbot_service

    class _FailingModerationClient:
        class _Moderations:
            def create(self, **kwargs):
                raise RuntimeError("rate-limited")

        moderations = _Moderations()

    flask_app.config["OPENAI_API_KEY"] = "sk-test"
    monkeypatch.setitem(chatbot_service._OPENAI_CAPABILITY_COOLDOWN_UNTIL, "moderation", 0.0)
    monkeypatch.setattr(
        "app.services.chatbot_service._openai_client",
        lambda: _FailingModerationClient(),
    )

    with flask_app.app_context():
        assert chatbot_service.moderate_message("teste") is False


def test_moderate_message_uses_cooldown_after_provider_error(flask_app, monkeypatch):
    import app.services.chatbot_service as chatbot_service

    calls = {"count": 0}

    class _FailingModerationClient:
        class _Moderations:
            def create(self, **kwargs):
                calls["count"] += 1
                raise RuntimeError("insufficient_quota")

        moderations = _Moderations()

    flask_app.config["OPENAI_API_KEY"] = "sk-test"
    flask_app.config["CHATBOT_OPENAI_COOLDOWN_SECONDS"] = 60
    monkeypatch.setitem(chatbot_service._OPENAI_CAPABILITY_COOLDOWN_UNTIL, "moderation", 0.0)
    monkeypatch.setattr(
        "app.services.chatbot_service._openai_client",
        lambda: _FailingModerationClient(),
    )

    with flask_app.app_context():
        assert chatbot_service.moderate_message("teste 1") is False
        assert chatbot_service.moderate_message("teste 2") is False

    assert calls["count"] == 1


def test_chatbot_stream_returns_sse_error_when_unexpected_exception_occurs(client, flask_app, monkeypatch):
    _enable_chatbot(flask_app)
    session_response = client.post("/api/chat/session", json={"source_page": "landing-faq"})
    conversation_id = session_response.json["conversation_id"]

    def _boom(**kwargs):
        raise RuntimeError("unexpected")
        yield ("done", {})

    monkeypatch.setattr("app.blueprints.ai_support.stream_user_message", _boom)

    response = client.post(
        "/api/chat/message/stream",
        json={
            "conversation_id": conversation_id,
            "message": "Teste",
            "page_context": "landing-faq",
            "locale": "pt-BR",
        },
    )

    text = response.data.decode("utf-8")
    assert response.status_code == 200
    assert "event: error" in text
    assert "Assistente indisponível no momento" in text


def test_stream_user_message_rebinds_detached_conversation(flask_app, db_session):
    from app.services.chatbot_service import get_or_create_conversation, stream_user_message

    _enable_chatbot(flask_app)

    with flask_app.app_context():
        conversation = get_or_create_conversation(
            user_id=None,
            anon_token_hash="anon-detached-test",
            source_page="landing-faq",
            locale="pt-BR",
        )
        conversation_id = conversation.id
        db_session.expunge(conversation)

        events = list(
            stream_user_message(
                conversation=conversation,
                message="Quais sao os planos disponiveis?",
                page_context="landing-faq",
                locale="pt-BR",
            )
        )

        rebound = db_session.get(ChatbotConversation, conversation_id)

    assert events[-1][0] == "done"
    assert rebound is not None
    assert rebound.turns_count == 1


def test_chatbot_conversation_is_persisted_for_authenticated_user(client, flask_app, db_session):
    _enable_chatbot(flask_app)
    user = User(email="chatbot-user@example.com", name="Chatbot User")
    user.set_password("password123")
    db_session.add(user)
    db_session.commit()

    login_response = client.post(
        "/login",
        data={"email": user.email, "password": "password123"},
        follow_redirects=False,
    )
    assert login_response.status_code == 302

    response = client.post("/api/chat/session", json={"source_page": "landing-faq"})

    assert response.status_code == 200
    conversation = db_session.get(ChatbotConversation, response.json["conversation_id"])
    assert conversation is not None
    assert conversation.user_id == user.id
    assert "terracota_chat_anon=" not in response.headers.get("Set-Cookie", "")
