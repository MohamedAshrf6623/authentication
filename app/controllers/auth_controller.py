from flask import request
from sqlalchemy import or_, func
from uuid import uuid4
import re
import secrets
import hashlib
import os
from datetime import datetime, timedelta

from app import db
from app.models.patient import Patient
from app.models.caregiver import CareGiver
from app.models.doctor import Doctor
from app.utils.jwt import create_access_token, decode_token, JWTError, revoke_token, build_password_signature
from app.utils.error_handler import handle_errors, AppError, ValidationError, AuthError, NotFoundError
from app.utils.response import success_response
from app.utils.email import send_password_reset_email
from app.utils.validation import (
    validate_payload,
    RegisterPatientPayload,
    RegisterDoctorPayload,
    RegisterCaregiverPayload,
    LoginPayload,
    ForgetPasswordPayload,
    ResetPasswordPayload,
    UpdateMyPasswordPayload,
)


def _patient_to_dict(patient: Patient):
    presc_list = []
    for pres in patient.prescriptions:
        schedule_time_str = pres.schedule_time.strftime('%H:%M:%S') if pres.schedule_time else None

        presc_list.append({
            'medicine_id': pres.medicine_id,
            'medicine_name': pres.medicine.name if pres.medicine else pres.medicine_name,
            'schedule_time': schedule_time_str,
            'alzhiemer_level': pres.alzhiemer_level,
            'notes': pres.notes
        })
    return {
        'patient_id': patient.patient_id,
        'name': patient.name,
        'email': patient.email,
        'age': patient.age,
        'gender': patient.gender,
        'phone': patient.phone,
        'city': patient.city,
        'address': patient.address,
        'age_category': patient.age_category,
        'hospital_address': patient.hospital_address,
        'doctor': (
            {
                'doctor_id': patient.doctor.doctor_id,
                'name': patient.doctor.name,
                'specialization': patient.doctor.specialization,
                'phone': patient.doctor.phone,
                'clinic_address': patient.doctor.clinic_address
            } if patient.doctor else None
        ),
        'care_giver': (
            {
                'care_giver_id': patient.care_giver.care_giver_id,
                'name': patient.care_giver.name,
                'relation': patient.care_giver.relation,
                'phone': patient.care_giver.phone,
                'city': patient.care_giver.city
            } if patient.care_giver else None
        ),
        'prescriptions': presc_list
    }


def _caregiver_to_dict(caregiver: CareGiver):
    return {
        'care_giver_id': caregiver.care_giver_id,
        'name': caregiver.name,
        'email': caregiver.email,
        'relation': caregiver.relation,
        'phone': caregiver.phone,
        'city': caregiver.city,
        'address': caregiver.address,
        'patients': [
            {
                'patient_id': p.patient_id,
                'name': p.name,
                'age': p.age,
                'gender': p.gender,
                'email': p.email
            } for p in caregiver.patients
        ]
    }


def _doctor_to_dict(doctor: Doctor):
    return {
        'doctor_id': doctor.doctor_id,
        'name': doctor.name,
        'email': doctor.email,
        'gender': doctor.gender,
        'specialization': doctor.specialization,
        'age': doctor.age,
        'phone': doctor.phone,
        'city': doctor.city,
        'clinic_address': doctor.clinic_address,
        'patients': [
            {
                'patient_id': p.patient_id,
                'name': p.name,
                'age': p.age,
                'gender': p.gender,
                'email': p.email
            } for p in doctor.patients
        ]
    }


def _issue_token(subject: str, role: str, password_hash: str | None = None):
    extra = None
    pwd_sig = build_password_signature(password_hash)
    if pwd_sig:
        extra = {'pwd_sig': pwd_sig}
    return create_access_token(subject, role=role, extra=extra)


def _normalize_email(email: str):
    return email.strip().lower()


def _missing_fields(data: dict, required: list[str]):
    return [f for f in required if not data.get(f)]


def _validate_email(email: str):
    return re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email)


def _model_by_role(role: str):
    role = (role or '').strip().lower()
    if role == 'patient':
        return Patient
    if role == 'doctor':
        return Doctor
    if role == 'caregiver':
        return CareGiver
    return None


def _subject_for_user(user_obj, role: str):
    if role == 'patient':
        return str(user_obj.patient_id)
    if role == 'doctor':
        return str(user_obj.doctor_id)
    return str(user_obj.care_giver_id)


def _public_user_payload(user_obj, role: str):
    if role == 'patient':
        return {'patient': _patient_to_dict(user_obj)}
    if role == 'doctor':
        return {'doctor': _doctor_to_dict(user_obj)}
    return {'caregiver': _caregiver_to_dict(user_obj)}


def _build_reset_url(raw_token: str):
    template = (
        os.getenv('MOBILE_RESET_PASSWORD_URL_TEMPLATE')
        or os.getenv('RESET_PASSWORD_DEEP_LINK_TEMPLATE')
        or 'alzaware://resetpassword?token={token}'
    )

    if '{token}' in template:
        return template.format(token=raw_token)

    separator = '&' if '?' in template else '?'
    return f'{template}{separator}token={raw_token}'


def _generate_reset_token_pair():
    raw_token = secrets.token_urlsafe(32)
    hashed_token = hashlib.sha256(raw_token.encode('utf-8')).hexdigest()
    return raw_token, hashed_token


def _resolve_user_by_email(email: str, role: str | None):
    if role:
        model = _model_by_role(role)
        if not model:
            raise ValidationError('Invalid role. Allowed: patient, doctor, caregiver')
        user_obj = model.query.filter(func.lower(model.email) == email).first()
        return user_obj, role

    matches = []
    patient = Patient.query.filter(func.lower(Patient.email) == email).first()
    if patient:
        matches.append((patient, 'patient'))
    doctor = Doctor.query.filter(func.lower(Doctor.email) == email).first()
    if doctor:
        matches.append((doctor, 'doctor'))
    caregiver = CareGiver.query.filter(func.lower(CareGiver.email) == email).first()
    if caregiver:
        matches.append((caregiver, 'caregiver'))

    if len(matches) > 1:
        raise ValidationError('Email exists in multiple accounts; provide role (patient/doctor/caregiver)')
    if len(matches) == 1:
        return matches[0]
    return None, None


def _register_patient(data: dict):
    required = ['name', 'email', 'password', 'doctor_id', 'care_giver_id']
    missing = _missing_fields(data, required)
    if missing:
        raise ValidationError(f'Missing required fields: {", ".join(missing)}', details={'fields': missing})

    email = _normalize_email(data['email'])
    if not _validate_email(email):
        raise ValidationError('Invalid email format')

    existing = Patient.query.filter(func.lower(Patient.email) == email).first()
    if existing:
        raise AppError('Email already registered', status_code=409)

    doctor = Doctor.query.filter_by(doctor_id=data['doctor_id']).first()
    if not doctor:
        raise ValidationError(f'Doctor with id {data["doctor_id"]} does not exist')

    caregiver = CareGiver.query.filter_by(care_giver_id=data['care_giver_id']).first()
    if not caregiver:
        raise ValidationError(f'CareGiver with id {data["care_giver_id"]} does not exist')

    patient = Patient(
        patient_id=data.get('patient_id') or str(uuid4()),
        name=data['name'],
        email=email,
        age=data.get('age'),
        gender=data.get('gender'),
        phone=data.get('phone'),
        chronic_disease=data.get('chronic_disease'),
        city=data.get('city'),
        address=data.get('address'),
        age_category=data.get('age_category') or 'Unknown',
        hospital_address=data.get('hospital_address') or 'Not specified',
        doctor_id=data['doctor_id'],
        care_giver_id=data['care_giver_id'],
    )
    patient.set_password(data['password'])
    db.session.add(patient)
    db.session.commit()

    token = _issue_token(str(patient.patient_id), 'patient', patient.password)
    return success_response(
        data={'token': token, 'patient': _patient_to_dict(patient)},
        message='Patient registered successfully',
        status_code=201,
    )


def _register_doctor(data: dict):
    required = ['name', 'email', 'password']
    missing = _missing_fields(data, required)
    if missing:
        raise ValidationError(f'Missing fields: {", ".join(missing)}', details={'fields': missing})

    email = _normalize_email(data['email'])
    if not _validate_email(email):
        raise ValidationError('Invalid email format')

    existing = Doctor.query.filter(func.lower(Doctor.email) == email).first()
    if existing:
        raise AppError('Email already registered', status_code=409)

    doctor = Doctor(
        doctor_id=data.get('doctor_id') or str(uuid4()),
        name=data['name'],
        email=email,
        gender=data.get('gender'),
        specialization=data.get('specialization'),
        age=data.get('age'),
        phone=data.get('phone'),
        city=data.get('city'),
        clinic_address=data.get('clinic_address'),
    )
    doctor.set_password(data['password'])
    db.session.add(doctor)
    db.session.commit()

    token = _issue_token(str(doctor.doctor_id), 'doctor', doctor.password)
    return success_response(
        data={'token': token, 'doctor': _doctor_to_dict(doctor)},
        message='Doctor registered successfully',
        status_code=201,
    )


def _register_caregiver(data: dict):
    required = ['name', 'email', 'password']
    missing = _missing_fields(data, required)
    if missing:
        raise ValidationError(f'Missing fields: {", ".join(missing)}', details={'fields': missing})

    email = _normalize_email(data['email'])
    if not _validate_email(email):
        raise ValidationError('Invalid email format')

    existing = CareGiver.query.filter(func.lower(CareGiver.email) == email).first()
    if existing:
        raise AppError('Email already registered', status_code=409)

    caregiver = CareGiver(
        care_giver_id=data.get('care_giver_id') or str(uuid4()),
        name=data['name'],
        email=email,
        relation=data.get('relation'),
        phone=data.get('phone'),
        city=data.get('city'),
        address=data.get('address'),
    )
    caregiver.set_password(data['password'])
    db.session.add(caregiver)
    db.session.commit()

    token = _issue_token(str(caregiver.care_giver_id), 'caregiver', caregiver.password)
    return success_response(
        data={'token': token, 'caregiver': _caregiver_to_dict(caregiver)},
        message='Caregiver registered successfully',
        status_code=201,
    )


@handle_errors('Register failed')
def register():
    data = validate_payload(RegisterPatientPayload, request.get_json() or {})
    return _register_patient(data)


@handle_errors('Register patient failed')
def register_patient():
    data = validate_payload(RegisterPatientPayload, request.get_json() or {})
    return _register_patient(data)


@handle_errors('Register doctor failed')
def register_doctor():
    data = validate_payload(RegisterDoctorPayload, request.get_json() or {})
    return _register_doctor(data)


@handle_errors('Register caregiver failed')
def register_caregiver():
    data = validate_payload(RegisterCaregiverPayload, request.get_json() or {})
    return _register_caregiver(data)


@handle_errors('Login failed')
def login():
    data = validate_payload(LoginPayload, request.get_json() or {})
    role = (data.get('role') or '').strip().lower()
    identifier = (data.get('email') or data.get('username') or data.get('name') or '').strip()
    password = data.get('password')
    if not identifier or not password:
        raise ValidationError('email/username and password are required')

    ident_lower = identifier.lower()

    user_obj = None
    user_role = None

    def _match_patient():
        return Patient.query.filter(or_(func.lower(Patient.email) == ident_lower, Patient.name == identifier)).first()

    def _match_doctor():
        return Doctor.query.filter(or_(func.lower(Doctor.email) == ident_lower, Doctor.name == identifier)).first()

    def _match_caregiver():
        return CareGiver.query.filter(or_(func.lower(CareGiver.email) == ident_lower, CareGiver.name == identifier)).first()

    if role == 'patient':
        candidate = _match_patient()
        if candidate and candidate.verify_password(password):
            user_obj, user_role = candidate, 'patient'
    elif role == 'doctor':
        candidate = _match_doctor()
        if candidate and candidate.verify_password(password):
            user_obj, user_role = candidate, 'doctor'
    elif role == 'caregiver':
        candidate = _match_caregiver()
        if candidate and candidate.verify_password(password):
            user_obj, user_role = candidate, 'caregiver'
    else:
        p = _match_patient()
        if p and p.verify_password(password):
            user_obj, user_role = p, 'patient'
        else:
            d = _match_doctor()
            if d and d.verify_password(password):
                user_obj, user_role = d, 'doctor'
            else:
                c = _match_caregiver()
                if c and c.verify_password(password):
                    user_obj, user_role = c, 'caregiver'

    if not user_obj:
        raise AuthError('invalid credentials')

    if hasattr(user_obj, 'active') and not user_obj.active:
        raise AuthError('Account is deactivated')

    if user_role == 'patient':
        token = _issue_token(str(user_obj.patient_id), user_role, user_obj.password)
        return success_response(
            data={'token': token, 'role': user_role, 'patient': _patient_to_dict(user_obj)},
            message='Login successful',
            status_code=200,
        )
    if user_role == 'doctor':
        token = _issue_token(str(user_obj.doctor_id), user_role, user_obj.password)
        return success_response(
            data={'token': token, 'role': user_role, 'doctor': _doctor_to_dict(user_obj)},
            message='Login successful',
            status_code=200,
        )

    token = _issue_token(str(user_obj.care_giver_id), user_role, user_obj.password)
    return success_response(
        data={'token': token, 'role': user_role, 'caregiver': _caregiver_to_dict(user_obj)},
        message='Login successful',
        status_code=200,
    )


@handle_errors('Logout failed')
def logout():
    token = _get_token_from_header()
    if not token:
        raise AuthError('Missing Bearer token')
    try:
        decode_token(token)
    except JWTError as e:
        raise AuthError(str(e)) from e

    revoke_token(token)
    return success_response(message='Logged out', status_code=200)


@handle_errors('Forgot password failed')
def forget_password():
    data = validate_payload(ForgetPasswordPayload, request.get_json() or {})

    # 1) Get email (and optional role) from request body
    email_raw = data.get('email')
    role = (data.get('role') or '').strip().lower() or None
    if not email_raw:
        raise ValidationError('email is required')

    email = _normalize_email(email_raw)
    if not _validate_email(email):
        raise ValidationError('Invalid email format')

    # 2) Get user by email (and role if provided)
    user_obj, resolved_role = _resolve_user_by_email(email, role)
    if not user_obj:
        return success_response(
            message='If your account exists, you will receive an email.',
            status_code=200,
        )

    # 3) Generate reset token and store hashed token + expiry
    raw_token, hashed_token = _generate_reset_token_pair()
    user_obj.password_reset_token = hashed_token
    user_obj.password_reset_expires = datetime.utcnow() + timedelta(minutes=10)
    db.session.commit()

    # 4) Send reset URL to user email
    reset_url = _build_reset_url(raw_token)
    send_password_reset_email(to_email=email, reset_url=reset_url)

    return success_response(
        message='If your account exists, you will receive an email.',
        data={'role': resolved_role},
        status_code=200,
    )


@handle_errors('Reset password failed')
def reset_password():
    data = validate_payload(ResetPasswordPayload, request.get_json() or {})

    # 1) Get token and new password data from body/query
    raw_token = (data.get('token') or request.args.get('token') or '').strip()
    new_password = data.get('password')

    if not raw_token:
        raise ValidationError('token is required')
    if not new_password:
        raise ValidationError('password is required')

    # 2) Hash token and find matching user with non-expired reset token
    hashed_token = hashlib.sha256(raw_token.encode('utf-8')).hexdigest()
    now_utc = datetime.utcnow()

    user_obj = (
        Patient.query.filter(
            Patient.password_reset_token == hashed_token,
            Patient.password_reset_expires > now_utc,
        ).first()
    )
    resolved_role = 'patient'

    if not user_obj:
        user_obj = (
            Doctor.query.filter(
                Doctor.password_reset_token == hashed_token,
                Doctor.password_reset_expires > now_utc,
            ).first()
        )
        resolved_role = 'doctor'

    if not user_obj:
        user_obj = (
            CareGiver.query.filter(
                CareGiver.password_reset_token == hashed_token,
                CareGiver.password_reset_expires > now_utc,
            ).first()
        )
        resolved_role = 'caregiver'

    if not user_obj:
        raise ValidationError('Token is invalid or has expired')

    # 3) Set new password and clear reset token fields
    user_obj.set_password(new_password)
    user_obj.password_reset_token = None
    user_obj.password_reset_expires = None
    db.session.commit()

    # 4) Log user in, send new JWT
    token = _issue_token(_subject_for_user(user_obj, resolved_role), resolved_role, user_obj.password)
    response_data = {'token': token, 'role': resolved_role}
    response_data.update(_public_user_payload(user_obj, resolved_role))

    return success_response(
        message='Password reset successful',
        data=response_data,
        status_code=200,
    )


@handle_errors('Update password failed')
def update_my_password():
    data = validate_payload(UpdateMyPasswordPayload, request.get_json() or {})

    current_password = data.get('password_current') or data.get('current_password')
    new_password = data.get('password') or data.get('new_password')
    confirm_password = data.get('confirm_password')

    if not current_password:
        raise ValidationError('current_password is required')
    if not new_password or not confirm_password:
        raise ValidationError('password and confirm_password are required')
    if new_password != confirm_password:
        raise ValidationError('Password and confirm_password do not match')

    token = _get_token_from_header()
    if not token:
        raise AuthError('Missing Bearer token')

    try:
        payload = decode_token(token)
    except JWTError as e:
        raise AuthError(str(e)) from e

    role = payload.get('role')
    sub = payload.get('sub')
    if role not in ('patient', 'doctor', 'caregiver'):
        raise AuthError('Invalid token role')

    # 1) Get user from collection
    if role == 'patient':
        user_obj = Patient.query.filter_by(patient_id=sub).first()
        not_found_message = 'Patient not found'
    elif role == 'doctor':
        user_obj = Doctor.query.filter_by(doctor_id=sub).first()
        not_found_message = 'Doctor not found'
    else:
        user_obj = CareGiver.query.filter_by(care_giver_id=sub).first()
        not_found_message = 'CareGiver not found'

    if not user_obj:
        raise NotFoundError(not_found_message)

    # 2) Check if POSTed current password is correct
    if not user_obj.verify_password(current_password):
        raise AuthError('Your current password is wrong.')

    # 3) If so, update password
    user_obj.set_password(new_password)
    db.session.commit()

    # 4) Log user in, send JWT
    new_token = _issue_token(_subject_for_user(user_obj, role), role, user_obj.password)
    response_data = {'token': new_token, 'role': role}
    response_data.update(_public_user_payload(user_obj, role))

    return success_response(
        message='Password updated successfully',
        data=response_data,
        status_code=200,
    )


def _get_token_from_header():
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        return auth_header.split(' ', 1)[1]
    data = request.get_json(silent=True) or {}
    body_token = data.get('token') or data.get('access_token') or data.get('bearer_token')
    if body_token:
        token_str = str(body_token).strip()
        if token_str.startswith('Bearer '):
            return token_str.split(' ', 1)[1]
        return token_str
    return None
