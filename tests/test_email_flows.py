"""
Tests for email flows: registration welcome email, OAuth welcome email,
and newsletter notification.
"""

import app.blueprints.auth as auth_mod
import app.blueprints.main as main_mod


def test_register_sends_welcome_email(client, monkeypatch):
    sent = []

    def fake_send_welcome_email(*, user_name: str, user_email: str):
        sent.append({"user_name": user_name, "user_email": user_email})
        return True

    monkeypatch.setattr(auth_mod, "validate_email", lambda value: value)
    monkeypatch.setattr(auth_mod, "send_welcome_email", fake_send_welcome_email)

    response = client.post(
        "/register",
        data={
            "name": "Alice",
            "email": "alice@example.com",
            "password": "12345678",
            "password_confirm": "12345678",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert len(sent) == 1
    assert sent[0] == {"user_name": "Alice", "user_email": "alice@example.com"}


def test_google_first_signup_sends_welcome_email(client, monkeypatch):
    sent = []

    def fake_send_welcome_email(*, user_name: str, user_email: str):
        sent.append({"user_name": user_name, "user_email": user_email})
        return True

    class FakeGoogleClient:
        @staticmethod
        def authorize_access_token():
            return {
                "userinfo": {
                    "email": "googleuser@example.com",
                    "name": "Google User",
                    "sub": "google-sub-123",
                }
            }

    class FakeOAuthRegistry:
        google = FakeGoogleClient()

    monkeypatch.setattr(auth_mod, "send_welcome_email", fake_send_welcome_email)
    monkeypatch.setattr(auth_mod, "oauth_registry", FakeOAuthRegistry())

    response = client.get("/auth/google/callback", follow_redirects=False)

    assert response.status_code == 302
    assert len(sent) == 1
    assert sent[0] == {
        "user_name": "Google User",
        "user_email": "googleuser@example.com",
    }


def test_newsletter_submit_sends_notification(client, monkeypatch):
    sent = []

    def fake_send_newsletter_notification(
        *, subscriber_email: str, notify_email: str
    ):
        sent.append(
            {
                "subscriber_email": subscriber_email,
                "notify_email": notify_email,
            }
        )
        return True

    monkeypatch.setattr(
        main_mod,
        "send_newsletter_notification",
        fake_send_newsletter_notification,
    )

    response = client.post(
        "/api/subscribe", json={"email": "lead@example.com"}
    )

    assert response.status_code == 200
    assert len(sent) == 1
    assert sent[0] == {
        "subscriber_email": "lead@example.com",
        "notify_email": "comercial@terracotabpo.com",
    }
