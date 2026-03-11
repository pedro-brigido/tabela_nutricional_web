"""
Auth blueprint: login, register, logout, and Google OAuth.
"""

import logging
from datetime import datetime, timezone
from urllib.parse import urlparse

from authlib.integrations.flask_client import OAuth
from email_validator import EmailNotValidError, validate_email
from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required, login_user, logout_user

from app.extensions import db, limiter
from app.models.user import User
from app.services.email_service import send_welcome_email

logger = logging.getLogger(__name__)

auth_bp = Blueprint("auth", __name__, url_prefix="")
oauth_registry = None

GOOGLE_METADATA_URL = (
    "https://accounts.google.com/.well-known/openid-configuration"
)


def _is_safe_redirect(target: str) -> bool:
    """Prevent open-redirect: only allow relative paths on the same host."""
    if not target:
        return False
    parsed = urlparse(target)
    return parsed.scheme == "" and parsed.netloc == ""


def init_oauth(app):
    """Register OAuth clients with the Flask app."""
    global oauth_registry
    oauth_registry = OAuth(app)
    oauth_registry.register(
        name="google",
        server_metadata_url=GOOGLE_METADATA_URL,
        client_kwargs={"scope": "openid email profile"},
    )
    return oauth_registry


# ---- Login / Logout --------------------------------------------------------


@auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("10/minute")
def login():
    if current_user.is_authenticated:
        return redirect(url_for("product.calculator"))
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
            flash(
                "Conta desativada. Entre em contato com o suporte.", "error"
            )
            return render_template("login.html")

        try:
            user.last_login_at = datetime.now(timezone.utc)
            user.login_count = (user.login_count or 0) + 1
            db.session.commit()
        except Exception:
            db.session.rollback()
            logger.exception("Failed to update login stats for %s", email)

        login_user(user)

        next_url = request.args.get("next", "")
        if not _is_safe_redirect(next_url):
            next_url = url_for("product.calculator")
        return redirect(next_url)
    return render_template("login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("main.index"))


# ---- Register ---------------------------------------------------------------


@auth_bp.route("/register", methods=["GET", "POST"])
@limiter.limit("5/minute")
def register():
    if current_user.is_authenticated:
        return redirect(url_for("product.calculator"))
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()[:255]
        email = (request.form.get("email") or "").strip().lower()[:255]
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

        try:
            user = User(email=email, name=name)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
        except Exception:
            db.session.rollback()
            logger.exception("Failed to create user %s", email)
            flash(
                "Erro ao criar sua conta. Tente novamente em alguns instantes.",
                "error",
            )
            return render_template("register.html")

        if not send_welcome_email(user_name=user.name, user_email=user.email):
            logger.warning("Welcome email failed for %s", user.email)
        login_user(user)
        return redirect(url_for("product.calculator"))
    return render_template("register.html")


# ---- Google OAuth -----------------------------------------------------------


@auth_bp.route("/auth/google")
def google_login():
    if current_user.is_authenticated:
        return redirect(url_for("product.calculator"))

    if not current_app.config.get("GOOGLE_CLIENT_ID") or not current_app.config.get(
        "GOOGLE_CLIENT_SECRET"
    ):
        logger.error(
            "Google OAuth credentials not configured – "
            "GOOGLE_CLIENT_ID or GOOGLE_CLIENT_SECRET is empty."
        )
        flash(
            "Login com Google não está disponível no momento. "
            "Por favor, use e-mail e senha.",
            "error",
        )
        return redirect(url_for("auth.login"))

    try:
        redirect_uri = url_for("auth.google_callback", _external=True)
        return oauth_registry.google.authorize_redirect(redirect_uri)
    except Exception:
        logger.exception("Failed to initiate Google OAuth redirect")
        flash("Falha ao iniciar login com Google. Tente novamente.", "error")
        return redirect(url_for("auth.login"))


@auth_bp.route("/auth/google/callback")
def google_callback():
    try:
        token = oauth_registry.google.authorize_access_token()
    except Exception:
        logger.exception("Google OAuth token exchange failed")
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
        flash(
            "O Google não forneceu seu e-mail. Use e-mail e senha para criar uma conta.",
            "error",
        )
        return redirect(url_for("auth.register"))

    try:
        # Returning Google user (matched by oauth_id)
        user = (
            db.session.query(User)
            .filter_by(oauth_provider="google", oauth_id=oauth_id)
            .first()
        )
        if user:
            user.last_login_at = datetime.now(timezone.utc)
            user.login_count = (user.login_count or 0) + 1
            db.session.commit()
            login_user(user)
            return redirect(url_for("product.calculator"))

        # Existing account with same email — link Google OAuth
        user = db.session.query(User).filter_by(email=email).first()
        if user:
            user.oauth_provider = "google"
            user.oauth_id = oauth_id
            user.email_verified = True
            user.email_verified_at = user.email_verified_at or datetime.now(
                timezone.utc
            )
            user.last_login_at = datetime.now(timezone.utc)
            user.login_count = (user.login_count or 0) + 1
            db.session.commit()
            login_user(user)
            return redirect(url_for("product.calculator"))

        # Brand-new user via Google
        user = User(
            email=email,
            name=name,
            oauth_provider="google",
            oauth_id=oauth_id,
            password_hash=None,
            email_verified=True,
            email_verified_at=datetime.now(timezone.utc),
        )
        db.session.add(user)
        db.session.commit()

        if not send_welcome_email(user_name=user.name, user_email=user.email):
            logger.warning(
                "Welcome email failed for new Google user %s", email
            )

        login_user(user)
        return redirect(url_for("product.calculator"))

    except Exception:
        db.session.rollback()
        logger.exception("Error during Google OAuth user lookup/creation")
        flash(
            "Ocorreu um erro ao processar seu login com Google. Tente novamente.",
            "error",
        )
        return redirect(url_for("auth.login"))


# ---- Forgot / Reset Password -----------------------------------------------


@auth_bp.route("/forgot-password", methods=["GET", "POST"])
@limiter.limit("3/hour")
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for("product.calculator"))

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()

        # Timing-safe: always show the same message
        user = db.session.query(User).filter_by(email=email).first()
        if user and user.is_active:
            from app.services.auth_service import generate_password_reset_token
            from app.services.email_service import send_email

            token = generate_password_reset_token(email)
            reset_url = url_for(
                "auth.reset_password", token=token, _external=True
            )
            send_email(
                subject="Redefinir senha — Terracota",
                body=(
                    f"Olá, {user.name}!\n\n"
                    f"Clique no link abaixo para redefinir sua senha:\n{reset_url}\n\n"
                    "Este link expira em 1 hora.\n\n"
                    "Se você não solicitou, ignore este e-mail.\n\n"
                    "Equipe Terracota"
                ),
                to_email=email,
            )

        flash(
            "Se o e-mail estiver cadastrado, enviaremos um link de redefinição.",
            "success",
        )
        return redirect(url_for("auth.forgot_password"))

    return render_template("auth/forgot_password.html")


@auth_bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    from app.services.auth_service import verify_password_reset_token

    email = verify_password_reset_token(token)
    if not email:
        flash("Link inválido ou expirado. Solicite novamente.", "error")
        return redirect(url_for("auth.forgot_password"))

    if request.method == "POST":
        password = request.form.get("password", "")
        password_confirm = request.form.get("password_confirm", "")

        if len(password) < 8:
            flash("A senha deve ter no mínimo 8 caracteres.", "error")
            return render_template("auth/reset_password.html", token=token)
        if password != password_confirm:
            flash("As senhas não coincidem.", "error")
            return render_template("auth/reset_password.html", token=token)

        user = db.session.query(User).filter_by(email=email).first()
        if not user:
            flash("Usuário não encontrado.", "error")
            return redirect(url_for("auth.login"))

        user.set_password(password)
        db.session.commit()
        flash("Senha redefinida com sucesso! Faça login.", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/reset_password.html", token=token)


# ---- Email Verification ----------------------------------------------------


@auth_bp.route("/verify-email/<token>")
def verify_email(token):
    from app.services.auth_service import verify_email_token
    from datetime import datetime, timezone

    email = verify_email_token(token)
    if not email:
        flash("Link de verificação inválido ou expirado.", "error")
        return redirect(url_for("main.index"))

    user = db.session.query(User).filter_by(email=email).first()
    if user and not user.email_verified:
        user.email_verified = True
        user.email_verified_at = datetime.now(timezone.utc)
        db.session.commit()

    flash("E-mail verificado com sucesso!", "success")
    return redirect(url_for("product.calculator"))


@auth_bp.route("/resend-verification", methods=["POST"])
@login_required
@limiter.limit("3/hour")
def resend_verification():
    if current_user.email_verified:
        flash("Seu e-mail já está verificado.", "success")
        return redirect(url_for("account.dashboard"))

    from app.services.auth_service import generate_email_verification_token
    from app.services.email_service import send_email

    token = generate_email_verification_token(current_user.email)
    verify_url = url_for("auth.verify_email", token=token, _external=True)
    send_email(
        subject="Verificar e-mail — Terracota",
        body=(
            f"Olá, {current_user.name}!\n\n"
            f"Clique no link abaixo para verificar seu e-mail:\n{verify_url}\n\n"
            "Equipe Terracota"
        ),
        to_email=current_user.email,
    )
    flash("E-mail de verificação reenviado.", "success")
    return redirect(url_for("account.dashboard"))
