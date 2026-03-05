"""Tests for TACO food composition search — backend module + API endpoint."""

import pytest

from tabela_nutricional.taco import search, get_by_id, get_categories, _strip_accents


# ---------------------------------------------------------------------------
# Unit tests for the taco.py module
# ---------------------------------------------------------------------------

class TestStripAccents:
    def test_removes_diacritics(self):
        assert _strip_accents("açúcar") == "acucar"
        assert _strip_accents("pão") == "pao"
        assert _strip_accents("café") == "cafe"

    def test_plain_ascii_unchanged(self):
        assert _strip_accents("arroz") == "arroz"


class TestTacoSearch:
    def test_empty_query_returns_empty(self):
        assert search("") == []
        assert search("  ") == []

    def test_single_char_returns_empty(self):
        assert search("a") == []

    def test_prefix_match(self):
        results = search("Arroz")
        assert len(results) > 0
        assert all("arroz" in r["name"].lower() for r in results)

    def test_accent_insensitive(self):
        results = search("acucar")
        names = [r["name"] for r in results]
        assert any("Açúcar" in n for n in names)

    def test_substring_match(self):
        results = search("integral")
        assert len(results) > 0
        assert any("integral" in r["name"].lower() for r in results)

    def test_limit_parameter(self):
        results = search("arroz", limit=3)
        assert len(results) <= 3

    def test_result_structure(self):
        results = search("farinha", limit=1)
        assert len(results) == 1
        food = results[0]
        assert "id" in food
        assert "name" in food
        assert "category" in food
        assert "per100g" in food
        n = food["per100g"]
        for key in ("energyKcal", "carbs", "proteins", "totalFat", "saturatedFat", "fiber", "sodium"):
            assert key in n


class TestTacoGetById:
    def test_existing_id(self):
        food = get_by_id(1)
        assert food is not None
        assert food["id"] == 1
        assert food["name"] == "Arroz, integral, cozido"

    def test_nonexistent_id(self):
        assert get_by_id(999999) is None


class TestTacoCategories:
    def test_returns_sorted_categories(self):
        cats = get_categories()
        assert len(cats) > 5
        assert cats == sorted(cats)
        assert "Cereais e derivados" in cats


# ---------------------------------------------------------------------------
# Integration test for the /api/taco/search endpoint
# ---------------------------------------------------------------------------

def _seed_plans(session):
    """Seed minimal plan data for test user creation."""
    from app.models.plan import Plan
    if not Plan.query.filter_by(slug="free").first():
        session.add(Plan(slug="free", name="Free", price_brl=0, is_active=True))
        session.commit()


def _make_user(session, email="taco@test.com"):
    from app.models.user import User
    user = User(email=email, name="Taco Tester")
    user.set_password("Test1234!")
    session.add(user)
    session.commit()
    return user


def _login(client, user_id):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user_id)


class TestTacoSearchAPI:
    def test_search_returns_results(self, client, flask_app):
        with flask_app.app_context():
            from app.extensions import db
            _seed_plans(db.session)
            user = _make_user(db.session)
            _login(client, user.id)

            resp = client.get("/api/taco/search?q=farinha")
            assert resp.status_code == 200
            data = resp.get_json()
            assert "results" in data
            assert len(data["results"]) > 0
            assert "farinha" in data["results"][0]["name"].lower()

    def test_search_respects_limit(self, client, flask_app):
        with flask_app.app_context():
            from app.extensions import db
            _seed_plans(db.session)
            user = _make_user(db.session, "taco2@test.com")
            _login(client, user.id)

            resp = client.get("/api/taco/search?q=arroz&limit=2")
            assert resp.status_code == 200
            data = resp.get_json()
            assert len(data["results"]) <= 2

    def test_search_empty_query(self, client, flask_app):
        with flask_app.app_context():
            from app.extensions import db
            _seed_plans(db.session)
            user = _make_user(db.session, "taco3@test.com")
            _login(client, user.id)

            resp = client.get("/api/taco/search?q=")
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["results"] == []

    def test_search_requires_login(self, client, flask_app):
        with flask_app.app_context():
            resp = client.get("/api/taco/search?q=arroz")
            assert resp.status_code in (302, 401)
