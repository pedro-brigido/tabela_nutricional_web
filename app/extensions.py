"""
Flask extensions — instantiated here, initialized in create_app().
"""

from flask_login import LoginManager
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect

db = SQLAlchemy()

login_manager = LoginManager()
login_manager.login_view = "auth.login"

csrf = CSRFProtect()

limiter = Limiter(key_func=get_remote_address)

migrate = Migrate()
