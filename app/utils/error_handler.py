from functools import wraps
from flask import current_app, jsonify
from pydantic import ValidationError as PydanticValidationError
from app import db
from app.utils.response import error_response


class AppError(Exception):
    def __init__(self, message: str, status_code: int = 400, code: str | None = None, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code
        self.details = details or {}


class ValidationError(AppError):
    def __init__(self, message: str = 'Validation failed', details: dict | None = None):
        super().__init__(message=message, status_code=400, code='VALIDATION_ERROR', details=details)


class AuthError(AppError):
    def __init__(self, message: str = 'Unauthorized', details: dict | None = None):
        super().__init__(message=message, status_code=401, code='AUTH_ERROR', details=details)


class NotFoundError(AppError):
    def __init__(self, message: str = 'Resource not found', details: dict | None = None):
        super().__init__(message=message, status_code=404, code='NOT_FOUND', details=details)


def handle_errors(message: str = 'Internal server error', status_code: int = 500):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except AppError as err:
                db.session.rollback()
                return error_response(
                    message=err.message,
                    status_code=err.status_code,
                    code=err.code,
                    details=err.details or None,
                )
            except PydanticValidationError as err:
                db.session.rollback()
                return jsonify(err.errors()), 422
            except Exception:
                db.session.rollback()
                current_app.logger.exception('Unhandled exception in %s', func.__name__)
                return error_response(
                    message=message,
                    status_code=status_code,
                    code='INTERNAL_SERVER_ERROR',
                )

        return wrapper

    return decorator
