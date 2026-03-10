"""
Flask CLI commands.
"""

import csv
import os
from pathlib import Path

import click
from flask import Flask

from app.plan_seed_data import PLANS_SEED


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

        stripe_price_map = {
            "flow_start": (
                app.config.get("STRIPE_PRICE_ID_FLOW_START")
                or os.environ.get("STRIPE_PRICE_ID_FLOW_START")
                or ""
            ).strip(),
            "flow_pro": (
                app.config.get("STRIPE_PRICE_ID_FLOW_PRO")
                or os.environ.get("STRIPE_PRICE_ID_FLOW_PRO")
                or ""
            ).strip(),
            "flow_studio": (
                app.config.get("STRIPE_PRICE_ID_FLOW_STUDIO")
                or os.environ.get("STRIPE_PRICE_ID_FLOW_STUDIO")
                or ""
            ).strip(),
        }

        for plan_data in _PLANS_SEED:
            plan_data = dict(plan_data)
            if plan_data["slug"] in stripe_price_map:
                plan_data["stripe_price_id"] = stripe_price_map[plan_data["slug"]] or None
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

    @app.cli.command("sync-stripe-prices")
    def sync_stripe_prices():
        """Sync STRIPE_PRICE_ID_* env vars into Plan.stripe_price_id."""
        from app.extensions import db
        from app.models.plan import Plan

        stripe_price_map = {
            "flow_start": (
                app.config.get("STRIPE_PRICE_ID_FLOW_START")
                or os.environ.get("STRIPE_PRICE_ID_FLOW_START")
                or ""
            ).strip(),
            "flow_pro": (
                app.config.get("STRIPE_PRICE_ID_FLOW_PRO")
                or os.environ.get("STRIPE_PRICE_ID_FLOW_PRO")
                or ""
            ).strip(),
            "flow_studio": (
                app.config.get("STRIPE_PRICE_ID_FLOW_STUDIO")
                or os.environ.get("STRIPE_PRICE_ID_FLOW_STUDIO")
                or ""
            ).strip(),
        }

        updated = 0
        for slug, price_id in stripe_price_map.items():
            if not price_id:
                continue
            plan = Plan.query.filter_by(slug=slug).first()
            if not plan:
                click.echo(f"Plan '{slug}' not found, skipping.")
                continue
            if plan.stripe_price_id != price_id:
                plan.stripe_price_id = price_id
                updated += 1
                click.echo(f"Updated plan '{slug}' with stripe price '{price_id}'.")
        db.session.commit()
        click.echo(f"Done. Updated {updated} plan(s).")

    # -----------------------------------------------------------------
    # Stripe webhook endpoint automation
    # -----------------------------------------------------------------
    WEBHOOK_EVENTS = [
        "checkout.session.completed",
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
        "invoice.payment_succeeded",
        "invoice.payment_failed",
    ]

    @app.cli.command("setup-stripe-webhook")
    @click.argument("webhook_url")
    @click.option(
        "--update-env",
        is_flag=True,
        default=False,
        help="Grava automaticamente o STRIPE_WEBHOOK_SECRET no .env",
    )
    def setup_stripe_webhook(webhook_url: str, update_env: bool):
        """Create (or update) a Stripe webhook endpoint for production.

        WEBHOOK_URL is the full public URL, e.g.
        https://rotulagem.terracotabpo.com/billing/webhook

        The signing secret (whsec_...) is printed to stdout.  Pass
        --update-env to patch the .env file automatically.
        """
        import stripe as stripe_mod

        secret_key = (
            app.config.get("STRIPE_SECRET_KEY")
            or os.environ.get("STRIPE_SECRET_KEY", "")
        ).strip()
        if not secret_key:
            click.echo("STRIPE_SECRET_KEY não encontrada. Configure no .env primeiro.")
            raise SystemExit(1)

        stripe_mod.api_key = secret_key

        # Check if an endpoint for this URL already exists
        existing_endpoints = stripe_mod.WebhookEndpoint.list(limit=100)
        endpoint = None
        for ep in existing_endpoints.auto_paging_iter():
            if ep.url == webhook_url:
                endpoint = ep
                break

        if endpoint:
            # Update enabled_events to ensure they match
            stripe_mod.WebhookEndpoint.modify(
                endpoint.id,
                enabled_events=WEBHOOK_EVENTS,
            )
            click.echo(f"Webhook endpoint já existe (id: {endpoint.id}).")
            click.echo(
                "O signing secret original não pode ser recuperado após a criação."
            )
            click.echo(
                "Se você perdeu o secret, delete o endpoint no Dashboard e rode "
                "este comando novamente para criar um novo."
            )
            click.echo(f"\nPara deletar: stripe webhook_endpoints delete {endpoint.id}")
            click.echo("Ou: Stripe Dashboard → Developers → Webhooks → endpoint → Delete")
            return

        # Create a new webhook endpoint
        new_ep = stripe_mod.WebhookEndpoint.create(
            url=webhook_url,
            enabled_events=WEBHOOK_EVENTS,
            description="Tabela Nutricional Web - auto-provisioned",
        )

        signing_secret = new_ep.secret
        click.echo(f"Webhook endpoint criado com sucesso (id: {new_ep.id}).")
        click.echo(f"\n  STRIPE_WEBHOOK_SECRET={signing_secret}\n")

        if update_env:
            _patch_env_file("STRIPE_WEBHOOK_SECRET", signing_secret)
            click.echo("✓ .env atualizado com o novo STRIPE_WEBHOOK_SECRET.")
        else:
            click.echo(
                "Copie o valor acima para o .env, ou rode novamente com "
                "--update-env para gravar automaticamente."
            )

    def _patch_env_file(key: str, value: str) -> None:
        """Replace or append KEY=value in the .env file at project root."""
        env_path = Path(__file__).resolve().parent.parent / ".env"
        if not env_path.exists():
            env_path.write_text(f"{key}={value}\n", encoding="utf-8")
            return

        lines = env_path.read_text(encoding="utf-8").splitlines(keepends=True)
        found = False
        new_lines = []
        for line in lines:
            stripped = line.lstrip()
            if stripped.startswith(f"{key}="):
                new_lines.append(f"{key}={value}\n")
                found = True
            else:
                new_lines.append(line)
        if not found:
            if new_lines and not new_lines[-1].endswith("\n"):
                new_lines.append("\n")
            new_lines.append(f"{key}={value}\n")
        env_path.write_text("".join(new_lines), encoding="utf-8")

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

    @app.cli.command("chatbot-sync-kb")
    def chatbot_sync_kb():
        """Sync chatbot knowledge documents and chunks."""
        from app.services.chatbot_service import sync_knowledge_base

        result = sync_knowledge_base()
        click.echo(
            "Knowledge synced. "
            f"created={result['created']} updated={result['updated']} chunks={result['chunks']}"
        )

    @app.cli.command("chatbot-reembed")
    @click.option(
        "--all",
        "embed_all",
        is_flag=True,
        default=False,
        help="Regera embeddings de todos os chunks, nao apenas dos faltantes.",
    )
    def chatbot_reembed(embed_all: bool):
        """Generate embeddings for chatbot knowledge chunks."""
        from app.services.chatbot_service import reembed_knowledge_base, sync_if_needed

        sync_if_needed()
        result = reembed_knowledge_base(only_missing=not embed_all)
        click.echo(f"Embeddings atualizados: {result['embedded']}")

    @app.cli.command("chatbot-prune")
    def chatbot_prune():
        """Delete expired chatbot conversations based on retention settings."""
        from app.services.chatbot_service import prune_expired_conversations

        deleted = prune_expired_conversations()
        click.echo(f"Conversas removidas: {deleted}")


_PLANS_SEED = PLANS_SEED
