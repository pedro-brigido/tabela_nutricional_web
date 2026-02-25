from app.models.plan import Plan


def test_pricing_shows_marketing_when_no_plans(client):
    resp = client.get("/pricing")
    assert resp.status_code == 200
    text = resp.data.decode("utf-8")
    assert "Planos ainda não foram carregados no banco" in text
    assert "Terracota Flow Pro" in text
    assert "Testar Unlimited" in text


def test_pricing_uses_db_plans_when_present(client, db_session):
    db_session.add_all(
        [
            Plan(
                slug="free",
                name="Free",
                price_brl=0,
                max_tables_per_month=1,
                max_ingredients_per_table=10,
                pulse_level="digest",
                display_order=0,
                is_active=True,
            ),
            Plan(
                slug="flow_start",
                name="Terracota Flow Start",
                price_brl=39.90,
                max_tables_per_month=3,
                max_ingredients_per_table=25,
                pulse_level="general",
                has_templates=True,
                has_pdf_export=True,
                pulse_has_alerts=True,
                display_order=1,
                is_active=True,
            ),
            Plan(
                slug="flow_pro",
                name="Terracota Flow Pro",
                price_brl=79.90,
                max_tables_per_month=10,
                max_ingredients_per_table=80,
                has_templates=True,
                has_pdf_export=True,
                has_png_export=True,
                has_version_history=True,
                pulse_level="pro",
                pulse_max_topics=5,
                pulse_has_alerts=True,
                display_order=2,
                is_active=True,
            ),
            Plan(
                slug="flow_studio",
                name="Terracota Flow Studio (Unlimited)",
                price_brl=199.90,
                max_tables_per_month=None,
                max_ingredients_per_table=None,
                has_templates=True,
                has_pdf_export=True,
                has_png_export=True,
                has_version_history=True,
                has_branding=True,
                pulse_level="advanced",
                pulse_max_topics=15,
                pulse_has_alerts=True,
                pulse_has_radar=True,
                display_order=3,
                is_active=True,
            ),
        ]
    )
    db_session.commit()

    resp = client.get("/pricing")
    assert resp.status_code == 200
    text = resp.data.decode("utf-8")
    assert "Planos ainda não foram carregados no banco" not in text
    assert "Terracota Flow Studio (Unlimited)" in text

