"""
Auth blueprint: login, register, logout, and Google OAuth.
"""

from authlib.integrations.flask_client import OAuth
from email_validator import EmailNotValidError, validate_email
from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from email_service import send_welcome_email
from models import User, db

auth_bp = Blueprint("auth", __name__, url_prefix="")
oauth_registry = None

GOOGLE_METADATA_URL = "https://accounts.google.com/.well-known/openid-configuration"


def init_oauth(app):
    """Register OAuth clients with the Flask app. Call from app.py after app creation."""
    global oauth_registry
    oauth_registry = OAuth(app)
    oauth_registry.register(
        name="google",
        server_metadata_url=GOOGLE_METADATA_URL,
        client_kwargs={"scope": "openid email profile"},
    )
    return oauth_registry


# ---------------------------------------------------------------------------
# Login / Logout
# ---------------------------------------------------------------------------


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("index"))
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        if not email or not password:
            flash("Preencha e-mail e senha.", "error")
            return render_template("login.html")
        try:
            validate_email(email)
        except EmailNotValidError:
            flash("E-mail inválido.", "error")
            return render_template("login.html")
        user = db.session.query(User).filter_by(email=email).first()
        if user is None or not user.check_password(password):
            flash("E-mail ou senha incorretos.", "error")
            return render_template("login.html")
        if not user.is_active:
            flash("Conta desativada. Entre em contato com o suporte.", "error")
            return render_template("login.html")
        login_user(user)
        next_url = request.args.get("next") or url_for("index")
        return redirect(next_url)
    return render_template("login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("index"))


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("index"))
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        password_confirm = request.form.get("password_confirm") or ""

        if not name:
            flash("Informe seu nome.", "error")
            return render_template("register.html")
        if not email:
            flash("Informe seu e-mail.", "error")
            return render_template("register.html")
        try:
            validate_email(email)
        except EmailNotValidError:
            flash("E-mail inválido.", "error")
            return render_template("register.html")
        if len(password) < 8:
            flash("A senha deve ter no mínimo 8 caracteres.", "error")
            return render_template("register.html")
        if password != password_confirm:
            flash("As senhas não coincidem.", "error")
            return render_template("register.html")

        if db.session.query(User).filter_by(email=email).first():
            flash("Já existe uma conta com este e-mail. Faça login.", "error")
            return redirect(url_for("auth.login"))

        user = User(email=email, name=name)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        send_welcome_email(user_name=user.name, user_email=user.email)
        login_user(user)
        return redirect(url_for("index"))
    return render_template("register.html")


# ---------------------------------------------------------------------------
# Google OAuth
# ---------------------------------------------------------------------------


@auth_bp.route("/auth/google")
def google_login():
    if current_user.is_authenticated:
        return redirect(url_for("index"))
    redirect_uri = url_for("auth.google_callback", _external=True)
    return oauth_registry.google.authorize_redirect(redirect_uri)


@auth_bp.route("/auth/google/callback")
def google_callback():
    try:
        token = oauth_registry.google.authorize_access_token()
    except Exception:
        flash("Falha ao conectar com Google. Tente novamente.", "error")
        return redirect(url_for("auth.login"))
    userinfo = token.get("userinfo")
    if not userinfo:
        flash("Não foi possível obter seus dados do Google.", "error")
        return redirect(url_for("auth.login"))

    email = (userinfo.get("email") or "").strip().lower()
    name = (userinfo.get("name") or email or "Usuário").strip()
    oauth_id = userinfo.get("sub")

    if not email:
        flash("O Google não forneceu seu e-mail. Use e-mail e senha para criar uma conta.", "error")
        return redirect(url_for("auth.register"))

    user = db.session.query(User).filter_by(oauth_provider="google", oauth_id=oauth_id).first()
    if user:
        login_user(user)
        return redirect(url_for("index"))

    user = db.session.query(User).filter_by(email=email).first()
    if user:
        user.oauth_provider = "google"
        user.oauth_id = oauth_id
        db.session.commit()
        login_user(user)
        return redirect(url_for("index"))

    user = User(
        email=email,
        name=name,
        oauth_provider="google",
        oauth_id=oauth_id,
        password_hash=None,
    )
    db.session.add(user)
    db.session.commit()
    send_welcome_email(user_name=user.name, user_email=user.email)
    login_user(user)
    return redirect(url_for("index"))
