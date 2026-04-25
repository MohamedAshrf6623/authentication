from flask import request
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from app import db
from app.controllers.auth_controller import (
    _caregiver_to_dict,
    _doctor_to_dict,
    _normalize_email,
    _patient_to_dict,
    _register_caregiver,
    _register_doctor,
    _register_patient,
    _validate_email,
)
from app.models.admin import Admin
from app.models.caregiver import CareGiver
from app.models.doctor import Doctor
from app.models.patient import Patient
from app.models.system_log import SystemLog
from app.utils.audit import record_system_log
from app.utils.error_handler import AppError, AuthError, NotFoundError, ValidationError, handle_errors
from app.utils.jwt import JWTError, decode_token
from app.utils.response import success_response


def _admin_to_dict(admin: Admin):
    return {
        'admin_id': admin.admin_id,
        'name': admin.name,
        'email': admin.email,
        'active': admin.active,
    }


def _get_bearer_token():
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        return auth_header.split(' ', 1)[1]
    data = request.get_json(silent=True) or {}
    token = data.get('token') or data.get('access_token') or data.get('bearer_token')
    if token:
        token_str = str(token).strip()
        if token_str.startswith('Bearer '):
            return token_str.split(' ', 1)[1]
        return token_str
    return None


def _require_admin():
    token = _get_bearer_token()
    if not token:
        raise AuthError('Missing Bearer token')
    try:
        payload = decode_token(token)
    except JWTError as exc:
        raise AuthError(str(exc)) from exc
    if payload.get('role') != 'admin' or not payload.get('sub'):
        raise AuthError('Admin access only')
    admin = Admin.query.filter_by(admin_id=payload['sub']).first()
    if not admin or not admin.active:
        raise NotFoundError('Admin not found')
    return admin


def _model_for_role(role: str):
    role = (role or '').strip().lower()
    if role == 'patient':
        return Patient
    if role == 'doctor':
        return Doctor
    if role == 'caregiver':
        return CareGiver
    return None


def _list_users_for_role(role: str):
    model = _model_for_role(role)
    if not model:
        raise ValidationError('role must be one of patient, doctor, caregiver')
    if role == 'patient':
        return [_patient_to_dict(user) for user in model.query.filter_by(active=True).all()]
    if role == 'doctor':
        return [_doctor_to_dict(user) for user in model.query.filter_by(active=True).all()]
    return [_caregiver_to_dict(user) for user in model.query.filter_by(active=True).all()]


def _fetch_user(role: str, user_id: str):
    model = _model_for_role(role)
    if not model:
        raise ValidationError('role must be one of patient, doctor, caregiver')
    id_field = 'patient_id' if role == 'patient' else 'doctor_id' if role == 'doctor' else 'care_giver_id'
    user = model.query.filter(getattr(model, id_field) == user_id).first()
    if not user:
        raise NotFoundError(f'{role.title()} not found')
    return user


@handle_errors('Fetch admin overview failed')
def overview():
    _require_admin()
    return success_response(
        data={
            'patients_count': Patient.query.filter_by(active=True).count(),
            'doctors_count': Doctor.query.filter_by(active=True).count(),
            'caregivers_count': CareGiver.query.filter_by(active=True).count(),
            'admins_count': Admin.query.filter_by(active=True).count(),
            'logs_count': SystemLog.query.count(),
        }
    )


@handle_errors('Fetch users failed')
def list_users(role: str | None = None):
    _require_admin()
    if role:
        return success_response(data={'role': role, 'users': _list_users_for_role(role)})
    return success_response(
        data={
            'patients': _list_users_for_role('patient'),
            'doctors': _list_users_for_role('doctor'),
            'caregivers': _list_users_for_role('caregiver'),
        }
    )


@handle_errors('Create user failed')
def create_user(role: str):
    _require_admin()
    payload = request.get_json(silent=True) or {}
    role = (role or '').strip().lower()

    if role == 'patient':
        return _register_patient(payload, issue_token=False, log_event=True)
    if role == 'doctor':
        return _register_doctor(payload, issue_token=False, log_event=True)
    if role == 'caregiver':
        return _register_caregiver(payload, issue_token=False, log_event=True)

    raise ValidationError('role must be patient, doctor, or caregiver')


@handle_errors('Update user email failed')
def update_user_email(role: str, user_id: str):
    _require_admin()
    payload = request.get_json(silent=True) or {}
    new_email = _normalize_email((payload.get('email') or '').strip())
    if not new_email:
        raise ValidationError('email is required')
    if not _validate_email(new_email):
        raise ValidationError('Invalid email format')

    user_obj = _fetch_user(role, user_id)
    model = _model_for_role(role)
    duplicate = model.query.filter(func.lower(model.email) == new_email).first()
    if duplicate:
        same_id = getattr(duplicate, 'patient_id', None) == user_id or getattr(duplicate, 'doctor_id', None) == user_id or getattr(duplicate, 'care_giver_id', None) == user_id
        if not same_id:
            raise ValidationError('Email already exists')

    old_email = user_obj.email
    user_obj.email = new_email
    db.session.commit()
    record_system_log(
        event_type='user_email_updated',
        message='User email updated by admin',
        actor_role='admin',
        target_role=role,
        target_id=user_id,
        target_email=new_email,
        details={'old_email': old_email, 'new_email': new_email},
    )
    db.session.commit()

    return success_response(
        data={'role': role, 'user_id': user_id, 'email': new_email},
        message='Email updated successfully',
    )


@handle_errors('Manage user account failed')
def manage_user_account(role: str, user_id: str):
    _require_admin()
    payload = request.get_json(silent=True) or {}
    action = (payload.get('action') or '').strip().lower()
    if action not in ('delete', 'disable', 'enable'):
        raise ValidationError('action must be one of: delete, disable, enable')

    user_obj = _fetch_user(role, user_id)

    if action == 'disable':
        if not getattr(user_obj, 'active', True):
            return success_response(message=f'{role.title()} already disabled')
        user_obj.active = False
        db.session.commit()
        record_system_log(
            event_type='user_disabled',
            message='User disabled by admin',
            actor_role='admin',
            target_role=role,
            target_id=user_id,
            target_email=getattr(user_obj, 'email', None),
        )
        db.session.commit()
        return success_response(message=f'{role.title()} disabled successfully')

    if action == 'enable':
        if getattr(user_obj, 'active', True):
            return success_response(message=f'{role.title()} already enabled')
        user_obj.active = True
        db.session.commit()
        record_system_log(
            event_type='user_enabled',
            message='User enabled by admin',
            actor_role='admin',
            target_role=role,
            target_id=user_id,
            target_email=getattr(user_obj, 'email', None),
        )
        db.session.commit()
        return success_response(message=f'{role.title()} enabled successfully')

    try:
        db.session.delete(user_obj)
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        raise AppError(
            message='Cannot delete this user because related records exist. Use action=disable instead.',
            status_code=409,
            code='CONFLICT',
        ) from exc

    record_system_log(
        event_type='user_deleted',
        message='User permanently deleted by admin',
        actor_role='admin',
        target_role=role,
        target_id=user_id,
        target_email=getattr(user_obj, 'email', None),
    )
    db.session.commit()
    return success_response(message=f'{role.title()} deleted permanently')


@handle_errors('Fetch logs failed')
def list_logs():
    _require_admin()
    event_type = (request.args.get('event_type') or '').strip().lower() or None
    query = SystemLog.query
    if event_type:
        query = query.filter(func.lower(SystemLog.event_type) == event_type)
    logs = query.order_by(SystemLog.created_at.desc()).limit(500).all()
    return success_response(
        data={
            'logs': [
                {
                    'log_id': log.log_id,
                    'event_type': log.event_type,
                    'message': log.message,
                    'actor_role': log.actor_role,
                    'actor_id': log.actor_id,
                    'target_role': log.target_role,
                    'target_id': log.target_id,
                    'target_email': log.target_email,
                    'details': log.details,
                    'source_ip': log.source_ip,
                    'created_at': log.created_at.isoformat() if log.created_at else None,
                }
                for log in logs
            ]
        }
    )


@handle_errors('Fetch patient login logs failed')
def patient_login_logs():
    _require_admin()
    logs = SystemLog.query.filter(func.lower(SystemLog.event_type) == 'patient_login').order_by(SystemLog.created_at.desc()).limit(500).all()
    return success_response(
        data={
            'logs': [
                {
                    'log_id': log.log_id,
                    'patient_id': log.target_id,
                    'email': log.target_email,
                    'message': log.message,
                    'created_at': log.created_at.isoformat() if log.created_at else None,
                    'source_ip': log.source_ip,
                }
                for log in logs
            ]
        }
    )


@handle_errors('Fetch new patient logs failed')
def new_patient_logs():
    _require_admin()
    logs = SystemLog.query.filter(func.lower(SystemLog.event_type).in_(['patient_registered', 'patient_created'])).order_by(SystemLog.created_at.desc()).limit(500).all()
    return success_response(
        data={
            'logs': [
                {
                    'log_id': log.log_id,
                    'patient_id': log.target_id,
                    'email': log.target_email,
                    'message': log.message,
                    'created_at': log.created_at.isoformat() if log.created_at else None,
                }
                for log in logs
            ]
        }
    )