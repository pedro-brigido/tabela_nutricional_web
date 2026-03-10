def test_help_page_renders(client):
    response = client.get("/help")

    assert response.status_code == 200
    text = response.data.decode("utf-8")
    assert "Central de Ajuda" in text


def test_contact_page_renders(client):
    response = client.get("/contact")

    assert response.status_code == 200
    text = response.data.decode("utf-8")
    assert "Fale Conosco" in text
    assert 'method="post" action="/contact"' in text


def test_contact_page_prefills_from_query_params(client):
    response = client.get(
        "/contact?category=other&subject=D%C3%BAvida+sobre+conformidade&source=faq"
    )

    assert response.status_code == 200
    text = response.data.decode("utf-8")
    assert "Dúvida sobre conformidade" in text
    assert "Origem: faq" in text


def test_contact_page_includes_conversation_id_in_handoff_prefill(client):
    response = client.get(
        "/contact?category=other&subject=Conversa+com+especialista+IA&conversation_id=abc-123"
    )

    assert response.status_code == 200
    text = response.data.decode("utf-8")
    assert "Conversa com especialista IA" in text
    assert "Conversation ID: abc-123" in text


def test_contact_page_accepts_async_json_submission(client, monkeypatch):
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


def test_faq_section_ctas_point_to_help_and_contact_pages(client):
    response = client.get("/")

    assert response.status_code == 200
    text = response.data.decode("utf-8")
    assert 'data-faq-contact-trigger' in text
    assert 'href="/contact?category=other&amp;subject=D%C3%BAvida+sobre+conformidade&amp;source=faq"' in text
    assert 'href="/help"' in text
    assert 'id="faq-contact-modal"' in text
    assert 'name="subject" value="Dúvida sobre conformidade (FAQ)"' in text


def test_faq_section_shows_chatbot_cta_when_feature_is_enabled(client, flask_app):
    flask_app.config["CHATBOT_ENABLED"] = True

    response = client.get("/")

    assert response.status_code == 200
    text = response.data.decode("utf-8")
    assert "Abrir assistente IA" in text
    assert "data-chatbot-trigger" in text
    assert 'id="faq-chatbot-modal"' in text
