from flask import request
from sqlalchemy import func

from app import db
from app.models.patient import Patient
from app.models.caregiver import CareGiver
from app.models.doctor import Doctor
from app.utils.jwt import decode_token, JWTError, revoke_token
from app.utils.error_handler import handle_errors, AuthError, ValidationError, NotFoundError
from app.utils.response import success_response


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


def _public_user_payload(user_obj, role: str):
    if role == 'patient':
        return {'patient': _patient_to_dict(user_obj)}
    if role == 'doctor':
        return {'doctor': _doctor_to_dict(user_obj)}
    return {'caregiver': _caregiver_to_dict(user_obj)}


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


@handle_errors('Fetch profile failed')
def me():
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

    if role == 'doctor':
        doctor = Doctor.query.filter_by(doctor_id=sub).first()
        if not doctor:
            raise NotFoundError('Doctor not found')
        if not doctor.active:
            raise AuthError('Account is deactivated')
        return success_response(data=_doctor_to_dict(doctor), message='Profile fetched', status_code=200)

    if role == 'caregiver':
        caregiver = CareGiver.query.filter_by(care_giver_id=sub).first()
        if not caregiver:
            raise NotFoundError('CareGiver not found')
        if not caregiver.active:
            raise AuthError('Account is deactivated')
        return success_response(data=_caregiver_to_dict(caregiver), message='Profile fetched', status_code=200)

    patient = Patient.query.filter_by(patient_id=sub).first()
    if not patient:
        raise NotFoundError('Patient not found')
    if not patient.active:
        raise AuthError('Account is deactivated')
    return success_response(data=_patient_to_dict(patient), message='Profile fetched', status_code=200)


@handle_errors('Update profile failed')
def updateme():
    data = request.get_json() or {}

    # 1) Create error if user POSTs password data
    if data.get('password') or data.get('confirm_password'):
        raise ValidationError(
            'This route is not for password updates. Please use /auth/updatemypassword.',
            details={'fields': ['password', 'confirm_password']}
        )

    # Prevent updates to foreign key fields
    if data.get('doctor_id') or data.get('care_giver_id'):
        raise ValidationError(
            'Cannot update doctor_id or care_giver_id. Contact support for association changes.',
            details={'fields': ['doctor_id', 'care_giver_id']}
        )

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

    # 2) Filtered out unwanted fields names that are not allowed to be updated
    if role == 'patient':
        allowed_fields = ['name', 'email', 'age', 'gender', 'phone', 'city', 'address', 'hospital_address', 'age_category']
        user_obj = Patient.query.filter_by(patient_id=sub).first()
        not_found_message = 'Patient not found'
    elif role == 'doctor':
        allowed_fields = ['name', 'email', 'age', 'gender', 'phone', 'city', 'specialization', 'clinic_address']
        user_obj = Doctor.query.filter_by(doctor_id=sub).first()
        not_found_message = 'Doctor not found'
    else:  # caregiver
        allowed_fields = ['name', 'email', 'phone', 'city', 'address', 'relation']
        user_obj = CareGiver.query.filter_by(care_giver_id=sub).first()
        not_found_message = 'CareGiver not found'

    if not user_obj:
        raise NotFoundError(not_found_message)

    if not user_obj.active:
        raise AuthError('Account is deactivated')

    # Filter to only allowed fields
    filtered_data = {k: v for k, v in data.items() if k in allowed_fields}

    # 3) Update user document
    for key, value in filtered_data.items():
        setattr(user_obj, key, value)
    db.session.commit()

    # Return updated user info
    response_data = {'role': role}
    response_data.update(_public_user_payload(user_obj, role))

    return success_response(
        message='Profile updated successfully',
        data=response_data,
        status_code=200,
    )


@handle_errors('Delete profile failed')
def deleteme():
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

    user_obj.active = False
    db.session.commit()
    revoke_token(token)

    return success_response(
        message='Account deactivated successfully',
        data={'role': role, 'active': user_obj.active},
        status_code=200,
    )
