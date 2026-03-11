"""
Integration tests for quota API endpoints and table generation flow.
Tests cover:
- GET /api/quota returns correct values per plan
- GET /api/tables/latest returns the most recent table
- POST /api/calculate includes quota warning when exhausted
- POST /api/tables enforces quota and idempotency
- Free user: 1 table allowed, then blocked
"""

from app.extensions import db
from app.models.plan import Plan
from app.models.user import User
from app.services.table_service import create_table


def _seed_plans(session):
    plans = [
        Plan(
            slug="free", name="Grátis", price_brl=0,
            max_tables_per_month=1, max_ingredients_per_table=10,
            display_order=0,
        ),
        Plan(
            slug="flow_start", name="Básico", price_brl=39.90,
            max_tables_per_month=3, max_ingredients_per_table=25,
            display_order=1,
        ),
    ]
    for p in plans:
        session.add(p)
    session.commit()


def _make_user(session, email="quota@test.com"):
    user = User(email=email, name="Quota Tester")
    user.set_password("password123")
    session.add(user)
    session.commit()
    return user


def _login(client, user_id):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user_id)
        sess["_fresh"] = True


# ---- GET /api/quota ----------------------------------------------------------


def test_quota_returns_correct_values_fresh_user(client, flask_app):
    with flask_app.app_context():
        _seed_plans(db.session)
        user = _make_user(db.session, "fresh@test.com")
        _login(client, user.id)

        resp = client.get("/app/api/quota")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["canCreate"] is True
        assert data["tablesCreated"] == 0
        assert data["tablesLimit"] == 1
        assert data["planName"] == "Grátis"
        assert data["planSlug"] == "free"


def test_quota_returns_false_after_limit_reached(client, flask_app):
    with flask_app.app_context():
        _seed_plans(db.session)
        user = _make_user(db.session, "limit@test.com")
        _login(client, user.id)

        # Create one table (free limit = 1)
        create_table(
            user_id=user.id, title="T1",
            product_data={}, ingredients_data=[], result_data={},
        )

        resp = client.get("/app/api/quota")
        data = resp.get_json()
        assert data["canCreate"] is False
        assert data["tablesCreated"] == 1
        assert data["tablesLimit"] == 1


# ---- GET /api/tables/latest --------------------------------------------------


def test_latest_table_returns_null_when_none(client, flask_app):
    with flask_app.app_context():
        _seed_plans(db.session)
        user = _make_user(db.session, "empty@test.com")
        _login(client, user.id)

        resp = client.get("/app/api/tables/latest")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["table"] is None


def test_latest_table_returns_most_recent(client, flask_app):
    with flask_app.app_context():
        _seed_plans(db.session)
        user = _make_user(db.session, "recent@test.com")
        _login(client, user.id)

        # Free plan: limit=1, but we seed plans with 1 table
        # Create one table
        create_table(
            user_id=user.id, title="My Product",
            product_data={"name": "Bolo"},
            ingredients_data=[{"name": "Farinha"}],
            result_data={"perPortion": {"energy": {"display": "120"}}},
        )

        resp = client.get("/app/api/tables/latest")
        data = resp.get_json()
        assert data["table"] is not None
        assert data["table"]["title"] == "My Product"
        assert "result_data" in data["table"]
        assert "product_data" in data["table"]
        assert "ingredients_data" in data["table"]


# ---- POST /api/calculate (quota warning) ------------------------------------


def test_calculate_includes_warning_when_quota_exhausted(client, flask_app):
    with flask_app.app_context():
        _seed_plans(db.session)
        user = _make_user(db.session, "calc-warn@test.com")
        _login(client, user.id)

        # Use up the quota
        create_table(
            user_id=user.id, title="Used",
            product_data={}, ingredients_data=[], result_data={},
        )

        # Calculate should still succeed but include warning
        payload = {
            "product": {"portionSize": 100},
            "ingredients": [
                {
                    "id": 1, "name": "Farinha", "quantity": 100,
                    "nutritionalInfo": {
                        "energyKcal": 350, "carbs": 76, "proteins": 10,
                        "totalFat": 1, "saturatedFat": 0, "transFat": 0,
                        "fiber": 2, "sodium": 1
                    }
                }
            ]
        }
        resp = client.post("/app/api/calculate", json=payload)
        assert resp.status_code == 200
        data = resp.get_json()
        assert "calculatedData" in data
        assert data.get("warning") == "QUOTA_EXHAUSTED"


def test_calculate_no_warning_when_quota_available(client, flask_app):
    with flask_app.app_context():
        _seed_plans(db.session)
        user = _make_user(db.session, "calc-ok@test.com")
        _login(client, user.id)

        payload = {
            "product": {"portionSize": 100},
            "ingredients": [
                {
                    "id": 1, "name": "Farinha", "quantity": 100,
                    "nutritionalInfo": {
                        "energyKcal": 350, "carbs": 76, "proteins": 10,
                        "totalFat": 1, "saturatedFat": 0, "transFat": 0,
                        "fiber": 2, "sodium": 1
                    }
                }
            ]
        }
        resp = client.post("/app/api/calculate", json=payload)
        assert resp.status_code == 200
        data = resp.get_json()
        assert "calculatedData" in data
        assert "warning" not in data


# ---- POST /api/tables (quota enforcement + idempotency) ----------------------


def test_save_table_succeeds_within_quota(client, flask_app):
    with flask_app.app_context():
        _seed_plans(db.session)
        user = _make_user(db.session, "save-ok@test.com")
        _login(client, user.id)

        payload = {
            "title": "My Saved Table",
            "product": {"name": "Bolo"},
            "ingredients": [{"name": "Farinha"}],
            "calculatedData": {
                "per100g": {"energy": {"display": "250"}},
                "perPortion": {"energy": {"display": "100"}},
            },
            "idempotencyKey": "unique-save-key-001"
        }
        resp = client.post("/app/api/tables", json=payload)
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["id"] is not None
        assert data["title"] == "My Saved Table"


def test_save_table_blocked_when_quota_exceeded(client, flask_app):
    with flask_app.app_context():
        _seed_plans(db.session)
        user = _make_user(db.session, "blocked@test.com")
        _login(client, user.id)

        # Use up quota
        create_table(
            user_id=user.id, title="Used",
            product_data={}, ingredients_data=[], result_data={},
        )

        payload = {
            "title": "Should Fail",
            "product": {},
            "ingredients": [],
            "calculatedData": {
                "per100g": {"energy": {"display": "250"}},
                "perPortion": {"energy": {"display": "100"}},
            },
            "idempotencyKey": "blocked-key-001"
        }
        resp = client.post("/app/api/tables", json=payload)
        assert resp.status_code == 403
        data = resp.get_json()
        assert data["code"] == "QUOTA_EXCEEDED"


def test_save_table_idempotency_no_double_count(client, flask_app):
    with flask_app.app_context():
        _seed_plans(db.session)
        user = _make_user(db.session, "idempotent@test.com")
        _login(client, user.id)

        payload = {
            "title": "Idempotent Table",
            "product": {"name": "Test"},
            "ingredients": [],
            "calculatedData": {
                "per100g": {"energy": {"display": "250"}},
                "perPortion": {"energy": {"display": "100"}},
            },
            "idempotencyKey": "idem-key-999"
        }
        resp1 = client.post("/app/api/tables", json=payload)
        assert resp1.status_code == 201
        id1 = resp1.get_json()["id"]

        # Same idempotency key should return the same table
        resp2 = client.post("/app/api/tables", json=payload)
        assert resp2.status_code == 201
        id2 = resp2.get_json()["id"]
        assert id1 == id2

        # Quota should still show 1 table created, not 2
        resp_q = client.get("/app/api/quota")
        assert resp_q.get_json()["tablesCreated"] == 1


# ---- Requires authentication ------------------------------------------------


def test_quota_requires_auth(client, flask_app):
    with flask_app.app_context():
        resp = client.get("/app/api/quota")
        assert resp.status_code in (401, 302)  # redirect to login or 401


def test_latest_requires_auth(client, flask_app):
    with flask_app.app_context():
        resp = client.get("/app/api/tables/latest")
        assert resp.status_code in (401, 302)


def test_calculate_rejects_non_list_ingredients(client, flask_app):
    with flask_app.app_context():
        _seed_plans(db.session)
        user = _make_user(db.session, "bad-ingredients@test.com")
        _login(client, user.id)
        payload = {
            "product": {"portionSize": 100},
            "ingredients": "not-a-list",
        }
        resp = client.post("/app/api/calculate", json=payload)
        assert resp.status_code == 400


def test_calculate_rejects_invalid_portion_size(client, flask_app):
    with flask_app.app_context():
        _seed_plans(db.session)
        user = _make_user(db.session, "bad-portion@test.com")
        _login(client, user.id)
        payload = {
            "product": {"portionSize": "abc"},
            "ingredients": [
                {"name": "Farinha", "quantity": 100, "nutritionalInfo": {"carbs": 10}}
            ],
        }
        resp = client.post("/app/api/calculate", json=payload)
        assert resp.status_code == 400


def test_calculate_rejects_negative_ingredient_values(client, flask_app):
    with flask_app.app_context():
        _seed_plans(db.session)
        user = _make_user(db.session, "negative-ingredient@test.com")
        _login(client, user.id)
        payload = {
            "product": {"portionSize": 100},
            "ingredients": [
                {
                    "name": "Farinha",
                    "quantity": -5,
                    "nutritionalInfo": {"carbs": 10, "proteins": 1},
                }
            ],
        }
        resp = client.post("/app/api/calculate", json=payload)
        assert resp.status_code == 400


def test_save_table_rejects_invalid_result_shape(client, flask_app):
    with flask_app.app_context():
        _seed_plans(db.session)
        user = _make_user(db.session, "invalid-result@test.com")
        _login(client, user.id)
        payload = {
            "title": "Invalid",
            "product": {"name": "Bolo"},
            "ingredients": [{"name": "Farinha"}],
            "calculatedData": {"energy": 100},
            "idempotencyKey": "invalid-result-key",
        }
        resp = client.post("/app/api/tables", json=payload)
        assert resp.status_code == 400
