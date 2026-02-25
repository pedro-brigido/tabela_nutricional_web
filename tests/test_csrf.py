import re

import pytest

import app.blueprints.auth as auth_mod
from app import create_app
from app.extensions import db as _db
from app.models.user import User


@pytest.fixture()
def csrf_app():
    app = create_app("testing")
    app.config.update(
        WTF_CSRF_ENABLED=True,
        TESTING=True,
    )
    with app.app_context():
        _db.create_all()
    yield app
    with app.app_context():
        _db.drop_all()


@pytest.fixture()
def csrf_client(csrf_app):
    return csrf_app.test_client()


def _extract_csrf_from_input(html: bytes) -> str:
    m = re.search(rb'name="csrf_token"\s+value="([^"]+)"', html)
    assert m, "CSRF input not found in HTML"
    return m.group(1).decode("utf-8")


def _extract_csrf_from_meta(html: bytes) -> str:
    m = re.search(rb'<meta\s+name="csrf-token"\s+content="([^"]+)"', html)
    assert m, "CSRF meta tag not found in HTML"
    return m.group(1).decode("utf-8")


def _create_user(csrf_app, *, email: str = "u@test.com", password: str = "password123"):
    with csrf_app.app_context():
        u = User(email=email, name="User")
        u.set_password(password)
        _db.session.add(u)
        _db.session.commit()


def _login(csrf_client):
    login_page = csrf_client.get("/login")
    token = _extract_csrf_from_input(login_page.data)
    resp = csrf_client.post(
        "/login",
        data={"csrf_token": token, "email": "u@test.com", "password": "password123"},
        follow_redirects=False,
    )
    assert resp.status_code == 302


def test_login_requires_csrf_when_enabled(csrf_app, csrf_client, monkeypatch):
    _create_user(csrf_app)
    monkeypatch.setattr(auth_mod, "validate_email", lambda value: value)

    # Missing token should be rejected
    resp = csrf_client.post(
        "/login",
        data={"email": "u@test.com", "password": "password123"},
        follow_redirects=False,
    )
    assert resp.status_code == 400

    # With token should succeed
    login_page = csrf_client.get("/login")
    token = _extract_csrf_from_input(login_page.data)
    resp = csrf_client.post(
        "/login",
        data={"csrf_token": token, "email": "u@test.com", "password": "password123"},
        follow_redirects=False,
    )
    assert resp.status_code == 302


def test_api_tables_requires_csrf_header(csrf_app, csrf_client, monkeypatch):
    _create_user(csrf_app)
    monkeypatch.setattr(auth_mod, "validate_email", lambda value: value)
    _login(csrf_client)

    home = csrf_client.get("/")
    token = _extract_csrf_from_meta(home.data)

    payload = {
        "title": "Tabela 1",
        "product": {"name": "Produto", "portionSize": 50, "portionDesc": "g"},
        "ingredients": [{"id": 1, "name": "Ingrediente", "quantity": 10}],
        "calculatedData": {"perPortion": {"energy": {"raw": 0, "display": 0, "vd": 0}}},
        "idempotencyKey": "test-key-1",
    }

    resp = csrf_client.post("/api/tables", json=payload)
    assert resp.status_code == 400

    resp = csrf_client.post(
        "/api/tables",
        json=payload,
        headers={"X-CSRFToken": token},
    )
    assert resp.status_code == 201

