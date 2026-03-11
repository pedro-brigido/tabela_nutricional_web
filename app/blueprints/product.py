"""
Product blueprint: authenticated product pages at /app prefix.
Calculator, tables, and main product experience.
"""

from flask import Blueprint, render_template
from flask_login import current_user, login_required

from app.services.usage_service import get_usage_summary

product_bp = Blueprint("product", __name__, url_prefix="/app")


@product_bp.route("/")
@login_required
def calculator():
    """Main product page: the nutritional calculator."""
    usage = get_usage_summary(current_user.id)
    return render_template("app/calculator.html", usage=usage)
