"""
Unit tests for TableService.
"""

from app.extensions import db
from app.models.plan import Plan
from app.models.user import User
from app.services.plan_service import assign_plan
from app.services.table_service import (
    create_table,
    delete_table,
    get_table,
    get_versions,
    list_tables,
)


def _seed_plans(session):
    plans = [
        Plan(slug="free", name="Free", price_brl=0, max_tables_per_month=2,
             max_ingredients_per_table=10, display_order=0),
        Plan(slug="flow_pro", name="Flow Pro", price_brl=79.90,
             max_tables_per_month=10, max_ingredients_per_table=80,
             has_version_history=True, display_order=2),
    ]
    for p in plans:
        session.add(p)
    session.commit()


def _make_user(session, email="table_test@example.com"):
    user = User(email=email, name="Table Tester")
    user.set_password("password123")
    session.add(user)
    session.commit()
    return user


def test_create_table_consumes_quota(flask_app):
    with flask_app.app_context():
        _seed_plans(db.session)
        user = _make_user(db.session)

        t1 = create_table(
            user_id=user.id,
            title="Table 1",
            product_data={"name": "Produto A"},
            ingredients_data=[{"name": "Ing1"}],
            result_data={"energy": 100},
        )
        assert t1 is not None
        assert t1.title == "Table 1"

        t2 = create_table(
            user_id=user.id,
            title="Table 2",
            product_data={},
            ingredients_data=[],
            result_data={},
        )
        assert t2 is not None

        # Third table should fail (free plan = 2 tables/month)
        t3 = create_table(
            user_id=user.id,
            title="Table 3",
            product_data={},
            ingredients_data=[],
            result_data={},
        )
        assert t3 is None


def test_idempotency_key_prevents_duplicate(flask_app):
    with flask_app.app_context():
        _seed_plans(db.session)
        user = _make_user(db.session)

        t1 = create_table(
            user_id=user.id,
            title="Idempotent",
            product_data={},
            ingredients_data=[],
            result_data={},
            idempotency_key="unique-key-123",
        )
        assert t1 is not None

        t2 = create_table(
            user_id=user.id,
            title="Idempotent Retry",
            product_data={},
            ingredients_data=[],
            result_data={},
            idempotency_key="unique-key-123",
        )
        # Should return the same table, not consume extra quota
        assert t2.id == t1.id


def test_list_tables(flask_app):
    with flask_app.app_context():
        _seed_plans(db.session)
        user = _make_user(db.session)

        create_table(
            user_id=user.id, title="A", product_data={},
            ingredients_data=[], result_data={},
        )
        create_table(
            user_id=user.id, title="B", product_data={},
            ingredients_data=[], result_data={},
        )

        result = list_tables(user.id)
        assert result.total == 2


def test_get_and_delete_table(flask_app):
    with flask_app.app_context():
        _seed_plans(db.session)
        user = _make_user(db.session)

        t = create_table(
            user_id=user.id, title="To Delete", product_data={},
            ingredients_data=[], result_data={},
        )
        assert get_table(t.id, user.id) is not None

        assert delete_table(t.id, user.id)
        assert get_table(t.id, user.id) is None


def test_get_table_respects_ownership(flask_app):
    with flask_app.app_context():
        _seed_plans(db.session)
        user1 = _make_user(db.session, "owner@test.com")
        user2 = _make_user(db.session, "other@test.com")

        t = create_table(
            user_id=user1.id, title="Owner Only", product_data={},
            ingredients_data=[], result_data={},
        )
        assert get_table(t.id, user1.id) is not None
        assert get_table(t.id, user2.id) is None


def test_create_table_saves_version_for_entitled_plan(flask_app):
    with flask_app.app_context():
        _seed_plans(db.session)
        user = _make_user(db.session, "versioned@test.com")
        assign_plan(user_id=user.id, plan_slug="flow_pro")

        table = create_table(
            user_id=user.id,
            title="Versioned Table",
            product_data={},
            ingredients_data=[],
            result_data={"per100g": {}, "perPortion": {}},
        )
        versions = get_versions(table.id, user.id)
        assert len(versions) == 1


def test_create_table_persists_servings_and_package_weight(flask_app):
    """Regression: servingsPerPackage and packageWeight must survive sanitization."""
    with flask_app.app_context():
        _seed_plans(db.session)
        user = _make_user(db.session, "persist@test.com")

        table = create_table(
            user_id=user.id,
            title="Servings Test",
            product_data={
                "name": "Produto B",
                "servingsPerPackage": "5",
                "packageWeight": "500",
                "portionSize": "100",
            },
            ingredients_data=[{"name": "Ing"}],
            result_data={"energy": 100},
        )
        assert table is not None
        saved = get_table(table.id, user.id)
        assert saved.product_data["servingsPerPackage"] == "5"
        assert saved.product_data["packageWeight"] == "500"
