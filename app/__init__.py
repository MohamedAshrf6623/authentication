from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from dotenv import load_dotenv
import os

# Global SQLAlchemy instance
(db, migrate) = (SQLAlchemy(), None)

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

    app.config['SQLALCHEMY_DATABASE_URI'] = _build_mssql_uri()
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key')

    db.init_app(app)
    global migrate
    migrate = Migrate(app, db)

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
