"""
Integration tests for billing blueprint endpoints.
"""

from types import SimpleNamespace

import app.blueprints.billing as billing_bp_mod
from app.extensions import db
from app.models.user import User
from app.services.stripe_service import ExistingSubscriptionError


def _make_user(email="billing@test.com"):
    user = User(email=email, name="Billing User")
    user.set_password("password123")
    db.session.add(user)
    db.session.commit()
    return user


def _login_session(client, user_id: int):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user_id)
        sess["_fresh"] = True


def test_billing_routes_disabled_when_feature_off(client, flask_app):
    # Explicitly disable Stripe
    flask_app.config["STRIPE_ENABLED"] = False

    # Unauthenticated: before_request aborts with 404 (runs before @login_required)
    response = client.get("/billing/success")
    assert response.status_code == 404

    # Authenticated: still 404 because billing is disabled
    with flask_app.app_context():
        user = _make_user("disabled@test.com")
        user_id = user.id
    _login_session(client, user_id)
    response = client.get("/billing/success")
    assert response.status_code == 404


def test_checkout_redirects_when_enabled(client, flask_app, monkeypatch):
    with flask_app.app_context():
        user = _make_user()
        user_id = user.id
    _login_session(client, user_id)

    with flask_app.app_context():
        flask_app.config["STRIPE_ENABLED"] = True

    monkeypatch.setattr(
        billing_bp_mod,
        "create_checkout_session",
        lambda **kwargs: "https://checkout.stripe.test/session",
    )

    response = client.post(
        "/billing/checkout", data={"plan_slug": "flow_pro"}, follow_redirects=False
    )
    assert response.status_code == 302
    assert "checkout.stripe.test/session" in response.location


def test_checkout_redirects_to_portal_on_existing_subscription(
    client, flask_app, monkeypatch
):
    with flask_app.app_context():
        user = _make_user("existing-sub@test.com")
        user_id = user.id
        flask_app.config["STRIPE_ENABLED"] = True
    _login_session(client, user_id)

    def _raise_existing(**kwargs):
        raise ExistingSubscriptionError("already subscribed")

    monkeypatch.setattr(billing_bp_mod, "create_checkout_session", _raise_existing)

    response = client.post(
        "/billing/checkout", data={"plan_slug": "flow_pro"}, follow_redirects=False
    )
    assert response.status_code == 302
    assert response.location.endswith("/billing/portal-redirect")


def test_cancel_subscription_route_updates_status(client, flask_app, monkeypatch):
    with flask_app.app_context():
        user = _make_user("cancel-route@test.com")
        user_id = user.id
        flask_app.config["STRIPE_ENABLED"] = True
    _login_session(client, user_id)

    monkeypatch.setattr(
        billing_bp_mod,
        "schedule_subscription_cancellation",
        lambda **kwargs: SimpleNamespace(cancel_at_period_end=True),
    )

    response = client.post(
        "/billing/cancel-subscription",
        data={"action": "cancel"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.location.endswith("/account/")


def test_webhook_invalid_signature_returns_400(client, flask_app, monkeypatch):
    with flask_app.app_context():
        flask_app.config["STRIPE_ENABLED"] = True

    monkeypatch.setattr(
        billing_bp_mod,
        "verify_webhook_signature",
        lambda payload, sig_header: (_ for _ in ()).throw(ValueError("bad sig")),
    )

    response = client.post("/billing/webhook", data=b"{}")
    assert response.status_code == 400
