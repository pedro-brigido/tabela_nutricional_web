from app.extensions import db
from app.models.support import SupportTicket
from app.models.user import User


def _make_user(session, email="support@test.com"):
    user = User(email=email, name="Support Tester")
    user.set_password("password123")
    session.add(user)
    session.commit()
    return user


def _login(client, user_id):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user_id)
        sess["_fresh"] = True


def test_ticket_list_renders_internal_create_form(client, flask_app):
    with flask_app.app_context():
        user = _make_user(db.session)
        _login(client, user.id)

    response = client.get("/support/tickets")

    assert response.status_code == 200
    html = response.data.decode("utf-8")
    assert "Abrir novo ticket" in html
    assert 'action="/support/tickets"' in html
    assert "Criar ticket" in html


def test_create_ticket_stays_within_ticket_list_flow(client, flask_app):
    with flask_app.app_context():
        user = _make_user(db.session, "support2@test.com")
        _login(client, user.id)

    response = client.post(
        "/support/tickets",
        data={
            "subject": "Dúvida de cobrança",
            "category": "billing",
            "message": "Preciso confirmar meu upgrade.",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    html = response.data.decode("utf-8")
    assert "Ticket criado com sucesso." in html
    assert "Dúvida de cobrança" in html

    with flask_app.app_context():
        ticket = db.session.query(SupportTicket).filter_by(subject="Dúvida de cobrança").one()
        assert ticket.category == "billing"
        assert ticket.message == "Preciso confirmar meu upgrade."
