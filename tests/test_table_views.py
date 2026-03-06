"""
Tests for account table view and tables list routes.
Covers:
- GET /account/tables — paginated list
- GET /account/tables/<id> — single table view with nutrition table rendered
- 404 for non-existent or other-user tables
- Unauthenticated access redirects to login
- Dashboard shows "Ver todas" link when > 5 tables
"""

from app.extensions import db
from app.models.plan import Plan
from app.models.user import User
from app.services.table_service import create_table


def _seed_plans(session):
    plans = [
        Plan(
            slug="free", name="Grátis", price_brl=0,
            max_tables_per_month=100, max_ingredients_per_table=10,
            display_order=0,
        ),
    ]
    for p in plans:
        session.add(p)
    session.commit()


def _make_user(session, email="view@test.com"):
    user = User(email=email, name="View Tester")
    user.set_password("password123")
    session.add(user)
    session.commit()
    return user


def _login(client, user_id):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user_id)
        sess["_fresh"] = True


def _create_sample_table(user_id, title="Bolo de Chocolate", key=None):
    return create_table(
        user_id=user_id,
        title=title,
        product_data={
            "portionSize": "60",
            "portionDesc": "1 fatia",
            "gluten": "Contém glúten",
            "allergens": "CONTÉM OVO E TRIGO",
        },
        ingredients_data=[
            {"name": "Farinha", "quantity": 100},
            {"name": "Açúcar", "quantity": 50},
        ],
        result_data={
            "perPortion": {
                "energy": {"raw": 150, "display": "150", "vd": 8},
                "carbs": {"display": "20", "vd": 7},
                "proteins": {"display": "3", "vd": 4},
                "totalFat": {"display": "5", "vd": 9},
                "saturatedFat": {"display": "2", "vd": 10},
                "transFat": {"display": "0", "vd": "**"},
                "fiber": {"display": "1", "vd": 4},
                "sodium": {"display": "50", "vd": 2},
            }
        },
        idempotency_key=key,
    )


# ---- GET /account/tables/<id> -----------------------------------------------


def test_view_table_shows_nutrition_data(client, flask_app):
    with flask_app.app_context():
        _seed_plans(db.session)
        user = _make_user(db.session, "view1@test.com")
        table = _create_sample_table(user.id, key="vt-1")
        _login(client, user.id)

        resp = client.get(f"/app/account/tables/{table.id}")
        assert resp.status_code == 200
        html = resp.data.decode()
        assert "Bolo de Chocolate" in html
        assert "Informação Nutricional" in html
        assert "Imprimir / PDF" in html
        assert "CONTÉM OVO E TRIGO" in html
        assert "Contém glúten" in html


def test_view_table_404_for_other_user(client, flask_app):
    with flask_app.app_context():
        _seed_plans(db.session)
        owner = _make_user(db.session, "owner@test.com")
        intruder = _make_user(db.session, "intruder@test.com")
        table = _create_sample_table(owner.id, key="vt-2")
        _login(client, intruder.id)

        resp = client.get(f"/app/account/tables/{table.id}")
        assert resp.status_code == 404


def test_view_table_404_nonexistent(client, flask_app):
    with flask_app.app_context():
        _seed_plans(db.session)
        user = _make_user(db.session, "view3@test.com")
        _login(client, user.id)

        resp = client.get("/app/account/tables/99999")
        assert resp.status_code == 404


def test_view_table_requires_login(client, flask_app):
    resp = client.get("/app/account/tables/1")
    assert resp.status_code in (302, 401)


# ---- GET /account/tables ----------------------------------------------------


def test_tables_list_empty(client, flask_app):
    with flask_app.app_context():
        _seed_plans(db.session)
        user = _make_user(db.session, "listempty@test.com")
        _login(client, user.id)

        resp = client.get("/app/account/tables")
        assert resp.status_code == 200
        html = resp.data.decode()
        assert "Nenhuma tabela ainda" in html


def test_tables_list_shows_items(client, flask_app):
    with flask_app.app_context():
        _seed_plans(db.session)
        user = _make_user(db.session, "listfull@test.com")
        _create_sample_table(user.id, title="Tabela A", key="list-a")
        _create_sample_table(user.id, title="Tabela B", key="list-b")
        _login(client, user.id)

        resp = client.get("/app/account/tables")
        assert resp.status_code == 200
        html = resp.data.decode()
        assert "Tabela A" in html
        assert "Tabela B" in html


def test_tables_list_requires_login(client, flask_app):
    resp = client.get("/app/account/tables")
    assert resp.status_code in (302, 401)


# ---- Dashboard "Ver todas" link -------------------------------------------


def test_dashboard_shows_ver_todas_when_many(client, flask_app):
    with flask_app.app_context():
        _seed_plans(db.session)
        user = _make_user(db.session, "dashlink@test.com")
        for i in range(6):
            _create_sample_table(user.id, title=f"T{i}", key=f"dash-{i}")
        _login(client, user.id)

        resp = client.get("/app/account/")
        assert resp.status_code == 200
        html = resp.data.decode()
        assert "Ver todas" in html


def test_dashboard_no_ver_todas_when_few(client, flask_app):
    with flask_app.app_context():
        _seed_plans(db.session)
        user = _make_user(db.session, "dashfew@test.com")
        _create_sample_table(user.id, title="Only One", key="dash-one")
        _login(client, user.id)

        resp = client.get("/app/account/")
        assert resp.status_code == 200
        html = resp.data.decode()
        assert "Ver todas" not in html


# ---- Billing button conditional (free user) --------------------------------


def test_dashboard_free_user_no_manage_billing(client, flask_app):
    """Free user without Stripe subscription should NOT see 'Gerenciar cobrança'."""
    with flask_app.app_context():
        _seed_plans(db.session)
        user = _make_user(db.session, "freeuser@test.com")
        _login(client, user.id)

        resp = client.get("/app/account/")
        assert resp.status_code == 200
        html = resp.data.decode()
        # Should not have the manage billing button
        assert "Gerenciar cobrança" not in html
