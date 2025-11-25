import os
import datetime as dt
import jwt
from typing import Set

DEFAULT_EXP_MINUTES = 60
_blacklist: Set[str] = set()

class JWTError(Exception):
    pass

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
    except jwt.InvalidTokenError as e:
        raise JWTError('Invalid token') from e

def revoke_token(token: str):
    _blacklist.add(token)

def is_revoked(token: str) -> bool:
    return token in _blacklist
