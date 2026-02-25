"""
Flask CLI commands.
"""

import csv
from pathlib import Path

import click
from flask import Flask


def _parse_bool(value: str) -> bool:
    if not value or not str(value).strip():
        return False
    v = str(value).strip().lower()
    return v in ("1", "true", "yes", "sim", "s", "on")


def _parse_int_or_none(value: str):
    if not value or not str(value).strip():
        return None
    try:
        return int(value.strip())
    except ValueError:
        return None


def _parse_decimal(value: str, default=0):
    if not value or not str(value).strip():
        return default
    try:
        return float(str(value).strip().replace(",", "."))
    except ValueError:
        return default


def register_cli(app: Flask) -> None:
    @app.cli.command("import-plans-csv")
    @click.argument("csv_path", type=click.Path(exists=True, path_type=Path))
    @click.option("--encoding", default="utf-8", help="Encoding do arquivo CSV.")
    def import_plans_csv(csv_path: Path, encoding: str):
        """Import plans from a CSV file (upsert by slug)."""
        from app.extensions import db
        from app.models.plan import Plan

        # Colunas esperadas (case-insensitive). Opcionais têm default.
        required = {"slug", "name"}
        optional = {
            "price_brl": ("price_brl", lambda v: _parse_decimal(v, 0)),
            "max_tables_per_month": ("max_tables_per_month", _parse_int_or_none),
            "max_ingredients_per_table": ("max_ingredients_per_table", _parse_int_or_none),
            "has_templates": ("has_templates", _parse_bool),
            "has_pdf_export": ("has_pdf_export", _parse_bool),
            "has_png_export": ("has_png_export", _parse_bool),
            "has_version_history": ("has_version_history", _parse_bool),
            "has_branding": ("has_branding", _parse_bool),
            "pulse_level": ("pulse_level", lambda v: (v or "").strip() or "none"),
            "pulse_max_topics": ("pulse_max_topics", lambda v: _parse_int_or_none(v) or 0),
            "pulse_has_alerts": ("pulse_has_alerts", _parse_bool),
            "pulse_has_radar": ("pulse_has_radar", _parse_bool),
            "is_active": ("is_active", lambda v: _parse_bool(v) if (v and str(v).strip()) else True),
            "display_order": ("display_order", lambda v: _parse_int_or_none(v) or 0),
        }

        with open(csv_path, encoding=encoding, newline="") as f:
            reader = csv.DictReader(f, skipinitialspace=True)
            if not reader.fieldnames:
                click.echo("CSV vazio ou sem cabeçalho.")
                raise SystemExit(1)
            headers = {h.strip().lower(): h for h in reader.fieldnames}
            for col in required:
                if col not in headers:
                    click.echo(f"Coluna obrigatória ausente no CSV: '{col}'.")
                    raise SystemExit(1)

            for row_num, row in enumerate(reader, start=2):
                slug = (row.get(headers.get("slug", "slug")) or "").strip()
                name = (row.get(headers.get("name", "name")) or "").strip()
                if not slug or not name:
                    click.echo(f"Linha {row_num}: slug e name são obrigatórios, ignorando.")
                    continue

                plan_data = {"slug": slug, "name": name}
                for col_lower, (attr, parser) in optional.items():
                    orig_col = headers.get(col_lower)
                    if orig_col is not None and orig_col in row:
                        try:
                            plan_data[attr] = parser(row[orig_col])
                        except Exception as e:
                            click.echo(f"Linha {row_num}, coluna '{orig_col}': {e}")
                            raise SystemExit(1)
                    elif attr in ["max_tables_per_month", "max_ingredients_per_table"]:
                        plan_data[attr] = None
                    elif attr == "pulse_level":
                        plan_data[attr] = "none"
                    elif attr in ["pulse_max_topics", "display_order"]:
                        plan_data[attr] = 0
                    elif attr == "price_brl":
                        plan_data[attr] = 0
                    elif attr == "is_active":
                        plan_data[attr] = True
                    else:
                        plan_data[attr] = False

                existing = Plan.query.filter_by(slug=slug).first()
                if existing:
                    for k, v in plan_data.items():
                        if k != "slug":
                            setattr(existing, k, v)
                    click.echo(f"  Updated plan '{slug}'.")
                else:
                    plan = Plan(**plan_data)
                    db.session.add(plan)
                    click.echo(f"  Created plan '{slug}'.")

        db.session.commit()
        click.echo("Done.")

    @app.cli.command("seed-plans")
    def seed_plans():
        """Seed the plans table with default tiers."""
        from app.extensions import db
        from app.models.plan import Plan

        for plan_data in _PLANS_SEED:
            existing = Plan.query.filter_by(slug=plan_data["slug"]).first()
            if existing:
                for k, v in plan_data.items():
                    if k == "slug":
                        continue
                    setattr(existing, k, v)
                existing.is_active = True
                click.echo(f"  Updated plan '{plan_data['slug']}'.")
            else:
                plan = Plan(**plan_data)
                plan.is_active = True
                db.session.add(plan)
                click.echo(f"  Created plan '{plan_data['slug']}'.")
        db.session.commit()
        click.echo("Done.")

    @app.cli.command("create-admin")
    @click.argument("email")
    def create_admin(email: str):
        """Promote an existing user to admin by email."""
        from app.extensions import db
        from app.models.user import User

        user = User.query.filter_by(email=email.strip().lower()).first()
        if not user:
            click.echo(f"User '{email}' not found.")
            raise SystemExit(1)
        user.is_admin = True
        db.session.commit()
        click.echo(f"User '{email}' is now admin.")

    @app.cli.command("backfill-free-plan")
    def backfill_free_plan():
        """Assign Free plan to all users without an active subscription."""
        from app.extensions import db
        from app.models.plan import Plan, Subscription
        from app.models.user import User

        free = Plan.query.filter_by(slug="free").first()
        if not free:
            click.echo("Free plan not found. Run 'flask seed-plans' first.")
            raise SystemExit(1)

        users_without_sub = (
            User.query.filter(
                ~User.id.in_(
                    db.session.query(Subscription.user_id).filter_by(status="active")
                )
            ).all()
        )

        count = 0
        for user in users_without_sub:
            sub = Subscription(
                user_id=user.id,
                plan_id=free.id,
                status="active",
                assigned_by="system",
                notes="Backfill: assigned Free plan",
            )
            db.session.add(sub)
            count += 1

        db.session.commit()
        click.echo(f"Assigned Free plan to {count} user(s).")


    @app.cli.command("anonymize-deleted")
    def anonymize_deleted():
        """Anonymize users soft-deleted more than 30 days ago."""
        from datetime import datetime, timedelta, timezone

        from app.extensions import db
        from app.models.user import User

        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        users = User.query.filter(
            User.deleted_at.isnot(None), User.deleted_at < cutoff
        ).all()

        count = 0
        for user in users:
            if user.email.startswith("deleted_"):
                continue
            user.email = f"deleted_{user.id}@anonymized.local"
            user.name = "Usuário removido"
            user.password_hash = None
            user.oauth_provider = None
            user.oauth_id = None
            count += 1

        db.session.commit()
        click.echo(f"Anonymized {count} user(s).")


_PLANS_SEED = [
    {
        "slug": "free",
        "name": "Free",
        "price_brl": 0,
        "max_tables_per_month": 1,
        "max_ingredients_per_table": 10,
        "pulse_level": "digest",
        "pulse_max_topics": 0,
        "pulse_has_alerts": False,
        "pulse_has_radar": False,
        "has_templates": False,
        "has_pdf_export": False,
        "has_png_export": False,
        "has_version_history": False,
        "has_branding": False,
        "display_order": 0,
    },
    {
        "slug": "flow_start",
        "name": "Terracota Flow Start",
        "price_brl": 39.90,
        "max_tables_per_month": 3,
        "max_ingredients_per_table": 25,
        "pulse_level": "general",
        "pulse_max_topics": 0,
        "pulse_has_alerts": True,
        "pulse_has_radar": False,
        "has_templates": True,
        "has_pdf_export": True,
        "has_png_export": False,
        "has_version_history": False,
        "has_branding": False,
        "display_order": 1,
    },
    {
        "slug": "flow_pro",
        "name": "Terracota Flow Pro",
        "price_brl": 79.90,
        "max_tables_per_month": 10,
        "max_ingredients_per_table": 80,
        "has_templates": True,
        "has_pdf_export": True,
        "has_png_export": True,
        "has_version_history": True,
        "has_branding": False,
        "pulse_level": "pro",
        "pulse_max_topics": 5,
        "pulse_has_alerts": True,
        "pulse_has_radar": False,
        "display_order": 2,
    },
    {
        "slug": "flow_studio",
        "name": "Terracota Flow Studio (Unlimited)",
        "price_brl": 199.90,
        "max_tables_per_month": None,
        "max_ingredients_per_table": None,
        "has_templates": True,
        "has_pdf_export": True,
        "has_png_export": True,
        "has_version_history": True,
        "has_branding": True,
        "pulse_level": "advanced",
        "pulse_max_topics": 15,
        "pulse_has_alerts": True,
        "pulse_has_radar": True,
        "display_order": 3,
    },
]
