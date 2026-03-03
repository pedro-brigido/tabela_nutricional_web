"""
Account blueprint: "Minha Conta" dashboard, settings, usage, upgrade.
"""

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.extensions import csrf, db, limiter
from app.models.user import User
from app.services.plan_service import (
    get_user_plan,
    get_user_subscription,
    list_plans,
)
from app.services.usage_service import get_usage, get_usage_summary
from app.services.table_service import list_tables, get_table

account_bp = Blueprint("account", __name__, url_prefix="/account")


@account_bp.route("/")
@login_required
def dashboard():
    """Account dashboard: plan, usage, recent tables."""
    plan = get_user_plan(current_user.id)
    usage_summary = get_usage_summary(current_user.id)
    recent = list_tables(current_user.id, page=1, per_page=5)
    return render_template(
        "account/dashboard.html",
        plan=plan,
        subscription=get_user_subscription(current_user.id),
        usage=usage_summary,
        recent_tables=recent.items,
        has_more_tables=recent.total > 5,
    )


@account_bp.route("/tables")
@login_required
def tables_list():
    """All tables, paginated."""
    page = request.args.get("page", 1, type=int)
    pagination = list_tables(current_user.id, page=page, per_page=20)
    return render_template(
        "account/tables_list.html",
        tables=pagination.items,
        pagination=pagination,
    )


@account_bp.route("/tables/<int:table_id>")
@login_required
def view_table(table_id):
    """View a single saved table (read-only, with print)."""
    from flask import abort

    table = get_table(table_id, current_user.id)
    if not table:
        abort(404)
    return render_template("account/table_view.html", table=table)


@account_bp.route("/usage")
@login_required
def usage():
    """Detailed monthly usage."""
    plan = get_user_plan(current_user.id)
    usage_summary = get_usage_summary(current_user.id)
    return render_template(
        "account/usage.html", plan=plan, usage=usage_summary
    )


@account_bp.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    """Edit profile: name."""
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()[:255]
        if not name:
            flash("Informe seu nome.", "error")
        else:
            current_user.name = name
            db.session.commit()
            flash("Dados atualizados.", "success")
        return redirect(url_for("account.settings"))
    return render_template("account/settings.html")


@account_bp.route("/change-password", methods=["POST"])
@login_required
def change_password():
    """Change password (requires current password)."""
    current_pw = request.form.get("current_password", "")
    new_pw = request.form.get("new_password", "")
    confirm_pw = request.form.get("confirm_password", "")

    if not current_user.check_password(current_pw):
        flash("Senha atual incorreta.", "error")
        return redirect(url_for("account.settings"))

    if len(new_pw) < 8:
        flash("A nova senha deve ter no mínimo 8 caracteres.", "error")
        return redirect(url_for("account.settings"))

    if new_pw != confirm_pw:
        flash("As senhas não coincidem.", "error")
        return redirect(url_for("account.settings"))

    current_user.set_password(new_pw)
    db.session.commit()
    flash("Senha alterada com sucesso.", "success")
    return redirect(url_for("account.settings"))


@account_bp.route("/upgrade")
@login_required
def upgrade():
    """Upgrade page: show plans."""
    plans = list_plans()
    current_plan = get_user_plan(current_user.id)
    return render_template(
        "account/upgrade.html", plans=plans, current_plan=current_plan
    )


@account_bp.route("/export-data", methods=["POST"])
@login_required
@limiter.limit("1/day")
def export_data():
    """Export user data as JSON (LGPD)."""
    from app.models.table import NutritionTable

    tables = NutritionTable.query.filter_by(user_id=current_user.id).all()
    data = {
        "user": {
            "id": current_user.id,
            "email": current_user.email,
            "name": current_user.name,
            "created_at": current_user.created_at.isoformat()
            if current_user.created_at
            else None,
        },
        "tables": [
            {
                "id": t.id,
                "title": t.title,
                "product_data": t.product_data,
                "ingredients_data": t.ingredients_data,
                "result_data": t.result_data,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in tables
        ],
    }
    return jsonify(data)


@account_bp.route("/delete", methods=["POST"])
@login_required
def delete_account():
    """Request account deletion (soft delete, LGPD)."""
    from datetime import datetime, timezone

    password = request.form.get("password", "")

    if current_user.password_hash and not current_user.check_password(password):
        flash("Senha incorreta.", "error")
        return redirect(url_for("account.settings"))

    current_user.deleted_at = datetime.now(timezone.utc)
    current_user.is_active = False
    db.session.commit()

    from flask_login import logout_user

    logout_user()
    flash("Sua conta foi marcada para exclusão.", "success")
    return redirect(url_for("main.index"))
