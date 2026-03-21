from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_limiter.errors import RateLimitExceeded
from flask_talisman import Talisman
from dotenv import load_dotenv
from limits.util import parse_many
import ast
import os
import re

from app.utils.response import error_response

# Global SQLAlchemy instance
(db, migrate) = (SQLAlchemy(), None)
limiter = Limiter(key_func=get_remote_address)
DEFAULT_RATE_LIMIT = '100 per minute'


def _parse_rate_limits(raw_value: str | None):
    """Normalize RATE_LIMIT env value into a list of limiter strings.

    Accepts values like:
      - "100 per hour"
      - "100 per hour; 10 per minute"
      - "['100 per hour']"
    """
    if raw_value is None:
        return [DEFAULT_RATE_LIMIT]

    value = str(raw_value).strip()
    if not value:
        return [DEFAULT_RATE_LIMIT]

    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        value = value[1:-1].strip()

    candidates: list[str] = []

    if value.startswith('[') and value.endswith(']'):
        try:
            parsed = ast.literal_eval(value)
            if isinstance(parsed, (list, tuple, set)):
                candidates = [str(item).strip() for item in parsed if str(item).strip()]
        except Exception:
            value = value[1:-1].strip()

    if not candidates:
        candidates = [
            part.strip().strip("'\"")
            for part in re.split(r'[;,\n]', value)
            if part.strip()
        ]

    if not candidates:
        candidates = []

    recovered_candidates: list[str] = []
    for item in candidates:
        cleaned = str(item).strip()
        if not cleaned:
            continue

        recovered = re.findall(r"\d+\s+per\s+[a-zA-Z]+", cleaned)
        if recovered:
            recovered_candidates.extend([entry.strip() for entry in recovered if entry.strip()])
            continue

        recovered_candidates.append(cleaned)

    candidates = recovered_candidates

    valid_limits: list[str] = []
    for item in candidates:
        cleaned = item.strip()
        if (cleaned.startswith('[') and cleaned.endswith(']')) or (cleaned.startswith('(') and cleaned.endswith(')')):
            try:
                nested = ast.literal_eval(cleaned)
                if isinstance(nested, (list, tuple, set)):
                    for nested_item in nested:
                        nested_text = str(nested_item).strip().strip("'\"")
                        if not nested_text:
                            continue
                        try:
                            parse_many(nested_text)
                            valid_limits.append(nested_text)
                        except Exception:
                            continue
                    continue
            except Exception:
                pass
        try:
            parse_many(cleaned)
            valid_limits.append(cleaned)
        except Exception:
            continue

    deduped: list[str] = []
    for limit in valid_limits:
        if limit not in deduped:
            deduped.append(limit)

    return deduped or [DEFAULT_RATE_LIMIT]


def _load_default_rate_limits():
    ratelimit_default = _parse_rate_limits(os.getenv('RATELIMIT_DEFAULT'))
    rate_limit_per_hour = _parse_rate_limits(os.getenv('RATE_LIMIT_PER_HOUR'))

    merged: list[str] = []
    for item in ratelimit_default + rate_limit_per_hour:
        if item not in merged:
            merged.append(item)

    return merged or [DEFAULT_RATE_LIMIT]

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
    default_rate_limits = _load_default_rate_limits()
    default_rate_limits_config = '; '.join(default_rate_limits)

    app.config['SQLALCHEMY_DATABASE_URI'] = _build_mssql_uri()
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key')
    app.config['RATELIMIT_DEFAULT'] = default_rate_limits_config
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
        limits_text = ', '.join(default_rate_limits)
        return error_response(
            message=f'Too many requests from this IP. Limit is {limits_text}.',
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

    from app.routes.gps_routes import gps_bp
    app.register_blueprint(gps_bp, url_prefix='/api')

    return app
