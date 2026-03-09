"""
Tests for the AI chat blueprint and service.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from app.models.chat import ChatMessage, ChatSession
from app.services.chat_service import ChatService, chat_service


class TestChatSession:
    """Chat session lifecycle."""

    def test_create_session(self, client):
        resp = client.post(
            "/api/chat/session",
            data=json.dumps({}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert "session_id" in data
        assert len(data["session_id"]) == 36  # UUID4

    def test_resume_session(self, client, db_session):
        # Create a session first
        session = ChatSession(id="test-session-123")
        db_session.add(session)
        db_session.commit()

        resp = client.post(
            "/api/chat/session",
            data=json.dumps({"session_id": "test-session-123"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert resp.get_json()["session_id"] == "test-session-123"

    def test_resume_nonexistent_creates_new(self, client):
        resp = client.post(
            "/api/chat/session",
            data=json.dumps({"session_id": "does-not-exist"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["session_id"] != "does-not-exist"


class TestChatMessage:
    """Chat message endpoint."""

    def test_message_requires_session_and_text(self, client):
        resp = client.post(
            "/api/chat/message",
            data=json.dumps({}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_message_too_long(self, client, db_session):
        session = ChatSession(id="sess-long")
        db_session.add(session)
        db_session.commit()

        resp = client.post(
            "/api/chat/message",
            data=json.dumps({
                "session_id": "sess-long",
                "message": "x" * 5001,
            }),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_message_unavailable_without_api_key(self, client, db_session):
        """When OPENAI_API_KEY is not set, the service returns 503."""
        session = ChatSession(id="sess-no-key")
        db_session.add(session)
        db_session.commit()

        resp = client.post(
            "/api/chat/message",
            data=json.dumps({
                "session_id": "sess-no-key",
                "message": "Quanto custa?",
            }),
            content_type="application/json",
        )
        # Without a real API key in test config, service is unavailable
        assert resp.status_code == 503

    def test_message_streams_response(self, client, db_session, flask_app):
        session = ChatSession(id="sess-stream")
        db_session.add(session)
        db_session.commit()

        def fake_stream(session, message):
            yield "Olá"
            yield "!"

        with patch.object(chat_service, "client", new=MagicMock()), \
             patch.object(chat_service, "chat_stream", side_effect=fake_stream):
            resp = client.post(
                "/api/chat/message",
                data=json.dumps({
                    "session_id": "sess-stream",
                    "message": "Oi",
                }),
                content_type="application/json",
            )
            assert resp.status_code == 200
            assert resp.content_type == "text/event-stream; charset=utf-8"

            text = resp.get_data(as_text=True)
            assert '"done": true' in text or '"done":true' in text


class TestChatServiceUnit:
    """Unit tests for ChatService."""

    def test_get_or_create_session_new(self, flask_app):
        with flask_app.app_context():
            svc = ChatService()
            session = svc.get_or_create_session()
            assert session.id is not None
            assert len(session.id) == 36

    def test_get_or_create_session_existing(self, flask_app, db_session):
        with flask_app.app_context():
            existing = ChatSession(id="existing-id")
            db_session.add(existing)
            db_session.commit()

            svc = ChatService()
            session = svc.get_or_create_session("existing-id")
            assert session.id == "existing-id"

    def test_cleanup_expired_sessions(self, flask_app, db_session):
        from datetime import datetime, timedelta, timezone

        with flask_app.app_context():
            old_session = ChatSession(
                id="old-sess",
                last_activity=datetime.now(timezone.utc) - timedelta(hours=48),
            )
            recent_session = ChatSession(id="recent-sess")
            db_session.add_all([old_session, recent_session])
            db_session.commit()

            # Add a message to the old session
            msg = ChatMessage(
                session_id="old-sess", role="user", content="test"
            )
            db_session.add(msg)
            db_session.commit()

            svc = ChatService()
            removed = svc.cleanup_expired_sessions(ttl_hours=24)
            assert removed == 1
            assert db_session.get(ChatSession, "old-sess") is None
            assert db_session.get(ChatSession, "recent-sess") is not None
            assert ChatMessage.query.filter_by(session_id="old-sess").count() == 0

    def test_build_messages_includes_system_and_history(self, flask_app, db_session):
        with flask_app.app_context():
            session = ChatSession(id="build-msg-test")
            db_session.add(session)
            db_session.commit()

            m1 = ChatMessage(session_id=session.id, role="user", content="Oi")
            m2 = ChatMessage(session_id=session.id, role="assistant", content="Olá!")
            db_session.add_all([m1, m2])
            db_session.commit()

            svc = ChatService()
            messages = svc._build_messages(session)
            assert messages[0]["role"] == "system"
            assert "Terracota" in messages[0]["content"]
            assert len(messages) == 3  # system + 2 history
            assert messages[1] == {"role": "user", "content": "Oi"}
            assert messages[2] == {"role": "assistant", "content": "Olá!"}
