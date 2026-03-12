from urllib.parse import parse_qs, urlsplit

from app.services.auth_service import generate_password_reset_token


def _assert_public_nav(text: str, *, same_page_links: bool) -> None:
    prefix = "#" if same_page_links else "/#"
    assert f'href="{prefix}como-funciona"' in text
    assert f'href="{prefix}beneficios"' in text
    assert f'href="{prefix}planos"' in text
    assert f'href="{prefix}faq"' in text
    assert f'href="{prefix}contato"' in text
    assert 'href="/privacy"' in text
    assert "Entrar" in text
    assert "Comece grátis" in text


def test_help_redirects_to_landing_faq(client):
    response = client.get("/help", follow_redirects=False)

    assert response.status_code == 301
    assert response.headers["Location"].endswith("/#faq")


def test_contact_get_redirects_to_landing_contact_preserving_query(client):
    response = client.get(
        "/contact?category=other&subject=D%C3%BAvida+sobre+conformidade&source=faq",
        follow_redirects=False,
    )

    assert response.status_code == 301
    location = urlsplit(response.headers["Location"])
    assert location.path == "/"
    assert location.fragment == "contato"
    assert parse_qs(location.query) == {
        "category": ["other"],
        "subject": ["Dúvida sobre conformidade"],
        "source": ["faq"],
    }


def test_landing_prefills_contact_from_query_params(client):
    response = client.get(
        "/?category=other&subject=D%C3%BAvida+sobre+conformidade&source=faq"
    )

    assert response.status_code == 200
    text = response.data.decode("utf-8")
    assert 'name="subject" value="Dúvida sobre conformidade"' in text
    assert 'name="source" value="faq"' in text
    assert "Origem: faq" in text


def test_landing_prefill_includes_conversation_id_in_contact_handoff(client):
    response = client.get(
        "/?category=other&subject=Conversa+com+especialista+IA&conversation_id=abc-123"
    )

    assert response.status_code == 200
    text = response.data.decode("utf-8")
    assert "Conversa com especialista IA" in text
    assert 'name="conversation_id" value="abc-123"' in text
    assert "Conversation ID: abc-123" in text


def test_contact_post_accepts_async_json_submission(client, monkeypatch):
    monkeypatch.setattr(
        "app.blueprints.support.send_email",
        lambda **kwargs: True,
    )

    response = client.post(
        "/contact",
        json={
            "name": "Pedro",
            "email": "pedro@example.com",
            "category": "other",
            "subject": "Conversa com especialista IA",
            "source": "chatbot",
            "conversation_id": "conv-123",
            "message": "Preciso de ajuda com meu fluxo.",
        },
        headers={"Accept": "application/json"},
    )

    assert response.status_code == 200
    assert response.json["ok"] is True


def test_public_nav_is_consistent_across_public_pages(client, flask_app):
    with flask_app.app_context():
        token = generate_password_reset_token("nav@test.com")

    pages = [
        ("/", True),
        ("/privacy", False),
        ("/login", False),
        ("/register", False),
        ("/forgot-password", False),
        (f"/reset-password/{token}", False),
    ]

    for path, same_page_links in pages:
        response = client.get(path)
        assert response.status_code == 200, path
        text = response.data.decode("utf-8")
        _assert_public_nav(text, same_page_links=same_page_links)


def test_landing_links_use_canonical_anchors_not_removed_public_pages(client):
    response = client.get("/")

    assert response.status_code == 200
    text = response.data.decode("utf-8")
    assert 'data-faq-contact-trigger' in text
    assert 'href="#contato"' in text
    assert 'href="/?category=other&amp;subject=Ajuda+via+chatbot+IA&amp;source=faq-chatbot#contato"' in text
    assert 'href="/help"' not in text
    assert 'href="/contact"' not in text
    assert 'id="faq-contact-modal"' in text
    assert 'id="faq-contact-subject"' in text


def test_faq_section_shows_chatbot_cta_when_feature_is_enabled(client, flask_app):
    flask_app.config["CHATBOT_ENABLED"] = True

    response = client.get("/")

    assert response.status_code == 200
    text = response.data.decode("utf-8")
    assert "Abrir assistente IA" in text
    assert "data-chatbot-trigger" in text
    assert 'id="faq-chatbot-modal"' in text
