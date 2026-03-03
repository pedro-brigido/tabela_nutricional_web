"""
Unit tests for stripe_service core behaviors.
"""

from app.extensions import db
from app.models.billing import StripeEvent
from app.models.plan import Plan, Subscription
from app.models.user import User
from app.services.stripe_service import (
    DuplicateSubscriptionError,
    ExistingSubscriptionError,
    apply_subscription_state,
    create_billing_portal_session,
    create_checkout_session,
    schedule_subscription_cancellation,
    handle_webhook_event,
)


def _seed_plans():
    db.session.add_all(
        [
            Plan(
                slug="free",
                name="Free",
                price_brl=0,
                max_tables_per_month=1,
                max_ingredients_per_table=10,
                display_order=0,
                is_active=True,
            ),
            Plan(
                slug="flow_start",
                name="Flow Start",
                price_brl=39.90,
                stripe_price_id="price_start_test",
                max_tables_per_month=3,
                max_ingredients_per_table=25,
                display_order=1,
                is_active=True,
            ),
            Plan(
                slug="flow_pro",
                name="Flow Pro",
                price_brl=79.90,
                stripe_price_id="price_pro_test",
                max_tables_per_month=10,
                max_ingredients_per_table=80,
                display_order=2,
                is_active=True,
            ),
        ]
    )
    db.session.commit()


def _make_user(email="stripe@test.com"):
    user = User(email=email, name="Stripe User", stripe_customer_id="cus_test_123")
    user.set_password("password123")
    db.session.add(user)
    db.session.commit()
    return user


def test_apply_subscription_state_active_and_cancelled(flask_app):
    with flask_app.app_context():
        _seed_plans()
        user = _make_user()

        sub = apply_subscription_state(
            user_id=user.id,
            plan_slug="flow_pro",
            stripe_status="active",
            stripe_subscription_id="sub_123",
            current_period_start=None,
            current_period_end=None,
            cancel_at_period_end=False,
            event_id="evt_active_1",
        )
        db.session.commit()
        assert sub.status == "active"
        assert sub.plan.slug == "flow_pro"
        assert sub.assigned_by == "stripe"

        sub2 = apply_subscription_state(
            user_id=user.id,
            plan_slug="free",
            stripe_status="canceled",
            stripe_subscription_id="sub_123",
            current_period_start=None,
            current_period_end=None,
            cancel_at_period_end=True,
            event_id="evt_cancel_1",
        )
        db.session.commit()
        assert sub2.status == "cancelled"
        assert sub2.plan.slug == "free"


def test_handle_webhook_event_is_idempotent(flask_app):
    with flask_app.app_context():
        _seed_plans()
        user = _make_user()

        event = {
            "id": "evt_duplicate_1",
            "type": "customer.subscription.updated",
            "livemode": False,
            "created": 1730000000,
            "data": {
                "object": {
                    "id": "sub_abc",
                    "customer": user.stripe_customer_id,
                    "status": "active",
                    "cancel_at_period_end": False,
                    "current_period_start": 1730000000,
                    "current_period_end": 1732600000,
                    "metadata": {"user_id": str(user.id)},
                    "items": {"data": [{"price": {"id": "price_pro_test"}}]},
                }
            },
        }

        handle_webhook_event(event)
        handle_webhook_event(event)

        assert StripeEvent.query.count() == 1


def test_create_checkout_session_blocks_existing_same_plan(flask_app):
    with flask_app.app_context():
        flask_app.config["STRIPE_ENABLED"] = True
        _seed_plans()
        user = _make_user("same-plan@test.com")
        flow_pro = Plan.query.filter_by(slug="flow_pro").first()
        db.session.add(
            Subscription(
                user_id=user.id,
                plan_id=flow_pro.id,
                status="active",
                stripe_subscription_id="sub_existing_same",
                assigned_by="stripe",
            )
        )
        db.session.commit()

        try:
            create_checkout_session(
                user=user,
                plan_slug="flow_pro",
                success_url="https://example.com/success",
                cancel_url="https://example.com/cancel",
            )
            assert False, "Expected DuplicateSubscriptionError"
        except DuplicateSubscriptionError:
            assert True


def test_create_checkout_session_blocks_existing_other_plan(flask_app):
    with flask_app.app_context():
        flask_app.config["STRIPE_ENABLED"] = True
        _seed_plans()
        user = _make_user("other-plan@test.com")
        flow_start = Plan.query.filter_by(slug="flow_start").first()
        db.session.add(
            Subscription(
                user_id=user.id,
                plan_id=flow_start.id,
                status="active",
                stripe_subscription_id="sub_existing_other",
                assigned_by="stripe",
            )
        )
        db.session.commit()

        try:
            create_checkout_session(
                user=user,
                plan_slug="flow_pro",
                success_url="https://example.com/success",
                cancel_url="https://example.com/cancel",
            )
            assert False, "Expected ExistingSubscriptionError"
        except ExistingSubscriptionError:
            assert True


def test_schedule_subscription_cancellation_updates_local_state(flask_app, monkeypatch):
    with flask_app.app_context():
        flask_app.config["STRIPE_ENABLED"] = True
        _seed_plans()
        user = _make_user("cancel@test.com")
        flow_pro = Plan.query.filter_by(slug="flow_pro").first()
        sub = Subscription(
            user_id=user.id,
            plan_id=flow_pro.id,
            status="active",
            stripe_subscription_id="sub_cancel_001",
            assigned_by="stripe",
        )
        db.session.add(sub)
        db.session.commit()

        class _FakeSubscriptionAPI:
            @staticmethod
            def modify(subscription_id, cancel_at_period_end):
                return {
                    "id": subscription_id,
                    "status": "active",
                    "cancel_at_period_end": cancel_at_period_end,
                    "current_period_end": None,
                }

        class _FakeStripe:
            Subscription = _FakeSubscriptionAPI

        monkeypatch.setattr("app.services.stripe_service._stripe_module", lambda: _FakeStripe)

        updated = schedule_subscription_cancellation(
            user=user,
            cancel_at_period_end=True,
        )
        assert updated.cancel_at_period_end is True


def test_create_billing_portal_session_bootstraps_customer(flask_app, monkeypatch):
    with flask_app.app_context():
        flask_app.config["STRIPE_ENABLED"] = True
        user = User(email="portal@test.com", name="Portal User", stripe_customer_id=None)
        user.set_password("password123")
        db.session.add(user)
        db.session.commit()

        class _FakeCustomerAPI:
            @staticmethod
            def create(**kwargs):
                return {"id": "cus_new_001"}

        class _FakeBillingPortalSessionAPI:
            @staticmethod
            def create(customer, return_url):
                return {"url": "https://billing.stripe.test/portal"}

        class _FakeBillingPortal:
            Session = _FakeBillingPortalSessionAPI

        class _FakeStripe:
            Customer = _FakeCustomerAPI
            billing_portal = _FakeBillingPortal

        monkeypatch.setattr("app.services.stripe_service._stripe_module", lambda: _FakeStripe)

        url = create_billing_portal_session(
            user=user,
            return_url="https://example.com/account",
        )

        assert url == "https://billing.stripe.test/portal"
        assert user.stripe_customer_id == "cus_new_001"
