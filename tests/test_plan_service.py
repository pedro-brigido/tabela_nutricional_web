"""
Unit tests for PlanService and UsageService.
"""

from app.extensions import db
from app.models.plan import Plan, Subscription, UsageRecord
from app.models.user import User
from app.services.plan_service import (
    assign_plan,
    get_user_plan,
    get_user_subscription,
    has_entitlement,
    list_plans,
)
from app.services.usage_service import (
    can_create_table,
    can_use_ingredients,
    consume_table_quota,
    current_period,
    get_usage,
    get_usage_summary,
)


def _seed_plans(session):
    plans = [
        Plan(slug="free", name="Grátis", price_brl=0, max_tables_per_month=1,
             max_ingredients_per_table=10, display_order=0),
        Plan(slug="flow_pro", name="Profissional", price_brl=79.90,
             max_tables_per_month=10, max_ingredients_per_table=80,
             has_templates=True, has_pdf_export=True, has_version_history=True,
             display_order=2),
        Plan(slug="flow_studio", name="Ilimitado", price_brl=199.90,
             max_tables_per_month=None, max_ingredients_per_table=None,
             has_branding=True, display_order=3),
    ]
    for p in plans:
        session.add(p)
    session.commit()
    return plans


def _make_user(session, email="test@example.com"):
    user = User(email=email, name="Test")
    user.set_password("password123")
    session.add(user)
    session.commit()
    return user


def test_get_user_plan_defaults_to_free(flask_app):
    with flask_app.app_context():
        _seed_plans(db.session)
        user = _make_user(db.session)
        plan = get_user_plan(user.id)
        assert plan.slug == "free"


def test_assign_plan_creates_subscription(flask_app):
    with flask_app.app_context():
        _seed_plans(db.session)
        user = _make_user(db.session)

        sub = assign_plan(user.id, "flow_pro", assigned_by="admin")
        assert sub.status == "active"
        assert sub.plan.slug == "flow_pro"

        plan = get_user_plan(user.id)
        assert plan.slug == "flow_pro"


def test_assign_plan_cancels_old_subscription(flask_app):
    with flask_app.app_context():
        _seed_plans(db.session)
        user = _make_user(db.session)

        assign_plan(user.id, "free")
        assign_plan(user.id, "flow_pro")

        old = Subscription.query.filter_by(
            user_id=user.id, status="cancelled"
        ).first()
        assert old is not None

        current = get_user_subscription(user.id)
        assert current.plan.slug == "flow_pro"


def test_has_entitlement(flask_app):
    with flask_app.app_context():
        _seed_plans(db.session)
        user = _make_user(db.session)

        assert not has_entitlement(user.id, "has_templates")

        assign_plan(user.id, "flow_pro")
        assert has_entitlement(user.id, "has_templates")
        assert has_entitlement(user.id, "has_pdf_export")


def test_list_plans_ordered(flask_app):
    with flask_app.app_context():
        _seed_plans(db.session)
        plans = list_plans()
        assert len(plans) == 3
        assert plans[0].slug == "free"
        assert plans[2].slug == "flow_studio"


def test_can_create_table_respects_limit(flask_app):
    with flask_app.app_context():
        _seed_plans(db.session)
        user = _make_user(db.session)

        assert can_create_table(user.id)
        assert consume_table_quota(user.id)
        assert not can_create_table(user.id)
        assert not consume_table_quota(user.id)


def test_unlimited_plan_has_no_table_limit(flask_app):
    with flask_app.app_context():
        _seed_plans(db.session)
        user = _make_user(db.session)
        assign_plan(user.id, "flow_studio")

        for _ in range(20):
            assert consume_table_quota(user.id)


def test_can_use_ingredients_limit(flask_app):
    with flask_app.app_context():
        _seed_plans(db.session)
        user = _make_user(db.session)

        assert can_use_ingredients(user.id, 10)
        assert not can_use_ingredients(user.id, 11)

        assign_plan(user.id, "flow_pro")
        assert can_use_ingredients(user.id, 80)
        assert not can_use_ingredients(user.id, 81)


def test_usage_summary(flask_app):
    with flask_app.app_context():
        _seed_plans(db.session)
        user = _make_user(db.session)
        consume_table_quota(user.id)

        summary = get_usage_summary(user.id)
        assert summary["tables_created"] == 1
        assert summary["tables_limit"] == 1
        assert summary["plan_slug"] == "free"
        assert summary["period"] == current_period()


def test_get_usage_creates_record(flask_app):
    with flask_app.app_context():
        _seed_plans(db.session)
        user = _make_user(db.session)

        usage = get_usage(user.id)
        db.session.commit()
        assert usage.tables_created == 0
        assert usage.period == current_period()
