import os
import datetime as dt
import hashlib
import hmac
import jwt
from typing import Set
from flask import request
from functools import wraps
from app.utils.response import error_response

DEFAULT_EXP_MINUTES = 60
_blacklist: Set[str] = set()

class JWTError(Exception):
    pass


def build_password_signature(password_hash: str | None):
    if not password_hash:
        return None
    secret = _get_secret().encode('utf-8')
    payload = password_hash.encode('utf-8')
    return hmac.new(secret, payload, hashlib.sha256).hexdigest()


def _to_unix_timestamp(value):
    if isinstance(value, dt.datetime):
        if value.tzinfo is not None:
            value = value.astimezone(dt.timezone.utc).replace(tzinfo=None)
        return int(value.timestamp())
    return None


def _load_current_user(payload: dict):
    role = payload.get('role')
    sub = payload.get('sub')
    if not role or not sub:
        raise JWTError('Invalid token payload')

    if role == 'patient':
        from app.models.patient import Patient
        return Patient.query.filter_by(patient_id=sub).first()
    if role == 'doctor':
        from app.models.doctor import Doctor
        return Doctor.query.filter_by(doctor_id=sub).first()
    if role == 'caregiver':
        from app.models.caregiver import CareGiver
        return CareGiver.query.filter_by(care_giver_id=sub).first()

    raise JWTError('Invalid token role')

def _get_secret():
    secret = os.getenv('JWT_SECRET') or os.getenv('SECRET_KEY')
    if not secret:
        raise JWTError('JWT secret not configured (set JWT_SECRET or SECRET_KEY).')
    return secret

def _get_exp_minutes(overridden: int | None = None) -> int:
    if overridden is not None:
        return overridden
    env_val = os.getenv('JWT_EXP_MINUTES')
    if env_val and env_val.isdigit():
        return int(env_val)
    return DEFAULT_EXP_MINUTES

def create_access_token(sub: str, role: str | None = None, extra: dict | None = None, expires_minutes: int | None = None):
    exp_minutes = _get_exp_minutes(expires_minutes)
    payload = {
        'sub': sub,
        'iat': int(dt.datetime.utcnow().timestamp()),
        'exp': int((dt.datetime.utcnow() + dt.timedelta(minutes=exp_minutes)).timestamp()),
    }
    if role:
        payload['role'] = role
    if extra:
        payload.update(extra)
    token = jwt.encode(payload, _get_secret(), algorithm='HS256')
    return token

def decode_token(token: str):
    try:
        if token in _blacklist:
            raise JWTError('Token revoked')
        return jwt.decode(token, _get_secret(), algorithms=['HS256'])
    except jwt.ExpiredSignatureError as e:
        raise JWTError('Token expired') from e
    except jwt.InvalidSignatureError as e:
        raise JWTError('Invalid signature') from e
    except Exception as e:
        raise JWTError(f'Token validation failed: {e}')

def revoke_token(token: str):
    _blacklist.add(token)

def _get_token_from_header():
    auth_header = request.headers.get('Authorization')
    if auth_header and auth_header.startswith('Bearer '):
        return auth_header.split(' ')[1]
    return None

def jwt_required():
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            token = _get_token_from_header()
            if not token:
                return error_response(
                    message='Missing Authorization Header',
                    status_code=401,
                    code='AUTH_ERROR',
                )
            try:
                payload = decode_token(token)
                current_user = _load_current_user(payload)
                if not current_user:
                    raise JWTError('User no longer exists')

                token_iat = payload.get('iat')
                password_changed_at = (
                    getattr(current_user, 'password_changed_at', None)
                    or getattr(current_user, 'passwordChangedAt', None)
                )
                changed_ts = _to_unix_timestamp(password_changed_at)

                if changed_ts and token_iat and changed_ts > int(token_iat):
                    raise JWTError('Password changed after token was issued')

                token_password_sig = payload.get('pwd_sig')
                current_password_sig = build_password_signature(getattr(current_user, 'password', None))
                if not token_password_sig:
                    raise JWTError('Token missing security claim; please log in again')
                if token_password_sig and current_password_sig:
                    if not hmac.compare_digest(token_password_sig, current_password_sig):
                        raise JWTError('Password changed after token was issued')

                # تخزين البيانات في الـ request لاستخدامها لاحقاً
                request.current_user_payload = payload
                request.current_user = current_user
            except JWTError as e:
                return error_response(
                    message=str(e),
                    status_code=401,
                    code='AUTH_ERROR',
                )
            return f(*args, **kwargs)
        return wrapper
    return decorator
