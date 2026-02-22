from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_limiter.errors import RateLimitExceeded
from flask_talisman import Talisman
from dotenv import load_dotenv
import os

from app.utils.response import error_response

# Global SQLAlchemy instance
(db, migrate) = (SQLAlchemy(), None)
limiter = Limiter(key_func=get_remote_address)

def _build_mssql_uri():
    """Build a SQL Server connection string from discrete environment variables if DATABASE_URL not supplied.

    Supported env vars:
      DATABASE_URL                Full override (if set we return it directly)
      MSSQL_SERVER                e.g. localhost or DESKTOP-ABC123\SQLEXPRESS
      MSSQL_DB                    Database name
      MSSQL_USER                  Username (omit for trusted connection)
      MSSQL_PASSWORD              Password
      MSSQL_DRIVER                Defaults to 'ODBC Driver 17 for SQL Server'
      MSSQL_TRUSTED               'true' to use Windows Integrated Security
    """
    full = os.getenv('DATABASE_URL')
    if full:
        return full

    server = os.getenv('MSSQL_SERVER')
    database = os.getenv('MSSQL_DB')
    driver = os.getenv('MSSQL_DRIVER', 'ODBC Driver 17 for SQL Server')
    trusted = os.getenv('MSSQL_TRUSTED', 'false').lower() == 'true'
    user = os.getenv('MSSQL_USER')
    password = os.getenv('MSSQL_PASSWORD')

    if not server or not database:
        # Fallback demo string (replace later by user)
        return 'mssql+pyodbc://USERNAME:PASSWORD@SERVER/DB_NAME?driver=ODBC+Driver+17+for+SQL+Server'

    if trusted:
        # Windows Integrated security
        return f"mssql+pyodbc://@{server}/{database}?driver={driver.replace(' ', '+')}&trusted_connection=yes"

    if not user or not password:
        raise RuntimeError('MSSQL_USER and MSSQL_PASSWORD must be set (or use MSSQL_TRUSTED=true).')

    return f"mssql+pyodbc://{user}:{password}@{server}/{database}?driver={driver.replace(' ', '+')}"


def create_app():
    """Application factory for Flask app."""
    load_dotenv()  # Load environment variables from .env if present
    app = Flask(__name__)
    default_rate_limit = os.getenv('RATE_LIMIT_PER_HOUR', '100 per hour')

    app.config['SQLALCHEMY_DATABASE_URI'] = _build_mssql_uri()
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key')
    app.config['RATELIMIT_DEFAULT'] = [default_rate_limit]
    app.config['RATELIMIT_STORAGE_URI'] = os.getenv('RATELIMIT_STORAGE_URI', 'memory://')

    db.init_app(app)
    limiter.init_app(app)
    Talisman(
        app,
        content_security_policy=None,
        force_https=False,
        strict_transport_security=False,
        session_cookie_secure=False,
    )
    global migrate
    migrate = Migrate(app, db)

    @app.errorhandler(RateLimitExceeded)
    def handle_rate_limit(_error):
        return error_response(
            message=f'Too many requests from this IP. Limit is {default_rate_limit}.',
            status_code=429,
            code='RATE_LIMIT_EXCEEDED',
        )

    # Import models to ensure SQLAlchemy can resolve relationships
    with app.app_context():
        from . import models  # noqa: F401

    # Register blueprints
    from .routes.auth_routes import auth_bp
    app.register_blueprint(auth_bp, url_prefix='/auth')
    
    from .routes.user_routes import user_bp
    app.register_blueprint(user_bp, url_prefix='/user')
    
    from app.routes.chat_routes import chat_bp
    app.register_blueprint(chat_bp, url_prefix='/chat')    

    return app
