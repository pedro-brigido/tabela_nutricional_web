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


def test_faq_section_ctas_point_to_help_and_contact_pages(client):
    response = client.get("/")

    assert response.status_code == 200
    text = response.data.decode("utf-8")
    assert 'data-faq-contact-trigger' in text
    assert 'href="/contact?category=other&amp;subject=D%C3%BAvida+sobre+conformidade&amp;source=faq"' in text
    assert 'href="/help"' in text
    assert 'id="faq-contact-modal"' in text
    assert 'name="subject" value="Dúvida sobre conformidade (FAQ)"' in text
