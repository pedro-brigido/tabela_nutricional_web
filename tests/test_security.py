"""
Security tests: headers, CSRF, open redirect protection.
"""

import app.blueprints.auth as auth_mod


def test_security_headers_present(client):
    resp = client.get("/health")
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"
    assert resp.headers.get("X-Frame-Options") == "DENY"
    assert resp.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
    assert "camera=()" in resp.headers.get("Permissions-Policy", "")
    assert "Content-Security-Policy" in resp.headers


def test_health_check_returns_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "ok"
    assert data["db"] == "ok"


def test_login_rejects_open_redirect(client, monkeypatch):
    """Login should not redirect to an external URL."""
    monkeypatch.setattr(auth_mod, "validate_email", lambda value: value)

    # Register a user first
    client.post(
        "/register",
        data={
            "name": "Safe",
            "email": "safe@test.com",
            "password": "password123",
            "password_confirm": "password123",
        },
    )
    # Logout
    client.get("/logout")

    # Try login with malicious next param
    resp = client.post(
        "/login?next=https://evil.com/steal",
        data={"email": "safe@test.com", "password": "password123"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    location = resp.headers.get("Location", "")
    assert "evil.com" not in location


def test_unauthenticated_api_returns_401(client):
    resp = client.post(
        "/api/calculate",
        json={"product": {}, "ingredients": []},
        headers={"Accept": "application/json"},
    )
    assert resp.status_code == 401


def test_404_returns_html(client):
    resp = client.get("/nonexistent-page")
    assert resp.status_code == 404
    assert b"404" in resp.data


def test_404_returns_json_for_api(client):
    resp = client.get(
        "/nonexistent-page",
        headers={"Accept": "application/json"},
    )
    assert resp.status_code == 404
    data = resp.get_json()
    assert "error" in data
