from flask import request
from sqlalchemy import func
from datetime import datetime

from app import db
from app.models.patient import Patient
from app.models.caregiver import CareGiver
from app.models.doctor import Doctor
from app.models.medicine import Medicine
from app.models.prescription import MPrescription
from app.utils.jwt import decode_token, JWTError, revoke_token
from app.utils.error_handler import handle_errors, AuthError, ValidationError, NotFoundError
from app.utils.response import success_response
from app.utils.validation import validate_payload, UpdateMePayload, AddPrescriptionPayload


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
        'chronic_disease': patient.chronic_disease,
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


def _parse_schedule_time(schedule_time_value: str):
    value = str(schedule_time_value or '').strip()
    if not value:
        raise ValidationError('schedule_time is required in HH:MM or HH:MM:SS format')

    for fmt in ('%H:%M:%S', '%H:%M'):
        try:
            return datetime.strptime(value, fmt).time()
        except ValueError:
            continue

    raise ValidationError('Invalid schedule_time format. Use HH:MM or HH:MM:SS')


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
    data = validate_payload(UpdateMePayload, request.get_json() or {})

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
        allowed_fields = ['name', 'email', 'age', 'gender', 'phone', 'chronic_disease', 'city', 'address', 'hospital_address', 'age_category']
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

    # Partial update only: keep existing DB values unless a non-null value is provided
    filtered_data = {
        key: value
        for key, value in data.items()
        if key in allowed_fields and value is not None
    }

    if not filtered_data:
        raise ValidationError(
            'No valid fields provided for update.',
            details={'allowed_fields': allowed_fields}
        )

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


@handle_errors('Add prescription failed')
def add_prescription():
    payload = validate_payload(AddPrescriptionPayload, request.get_json() or {})

    token = _get_token_from_header()
    if not token:
        raise AuthError('Missing Bearer token')

    try:
        token_payload = decode_token(token)
    except JWTError as e:
        raise AuthError(str(e)) from e

    role = token_payload.get('role')
    doctor_id = token_payload.get('sub')
    if role != 'doctor':
        raise AuthError('Only doctors can add prescriptions')

    doctor = Doctor.query.filter_by(doctor_id=doctor_id).first()
    if not doctor:
        raise NotFoundError('Doctor not found')
    if not doctor.active:
        raise AuthError('Account is deactivated')

    patient = Patient.query.filter_by(patient_id=payload['patient_id']).first()
    if not patient:
        raise NotFoundError('Patient not found')
    if not patient.active:
        raise ValidationError('Patient account is deactivated')
    if patient.doctor_id != doctor_id:
        raise AuthError('You can only add prescriptions for your own patients')

    medicine = Medicine.query.filter_by(medicine_id=payload['medicine_id']).first()
    if not medicine:
        raise NotFoundError('Medicine not found')

    schedule_time = _parse_schedule_time(payload['schedule_time'])

    existing = MPrescription.query.filter_by(
        patient_id=payload['patient_id'],
        medicine_id=payload['medicine_id'],
    ).first()

    if existing:
        existing.medicine_name = medicine.name
        existing.schedule_time = schedule_time
        existing.alzhiemer_level = payload.get('alzhiemer_level')
        existing.notes = payload.get('notes')
        message = 'Prescription updated successfully'
        prescription_obj = existing
    else:
        prescription_obj = MPrescription(
            patient_id=payload['patient_id'],
            medicine_id=payload['medicine_id'],
            medicine_name=medicine.name,
            schedule_time=schedule_time,
            alzhiemer_level=payload.get('alzhiemer_level'),
            notes=payload.get('notes'),
        )
        db.session.add(prescription_obj)
        message = 'Prescription added successfully'

    db.session.commit()

    return success_response(
        message=message,
        data={
            'patient_id': prescription_obj.patient_id,
            'medicine_id': prescription_obj.medicine_id,
            'medicine_name': prescription_obj.medicine_name,
            'schedule_time': prescription_obj.schedule_time.strftime('%H:%M:%S') if prescription_obj.schedule_time else None,
            'alzhiemer_level': prescription_obj.alzhiemer_level,
            'notes': prescription_obj.notes,
        },
        status_code=201 if message == 'Prescription added successfully' else 200,
    )


@handle_errors('Fetch prescriptions failed')
def my_prescriptions():
    token = _get_token_from_header()
    if not token:
        raise AuthError('Missing Bearer token')

    try:
        token_payload = decode_token(token)
    except JWTError as e:
        raise AuthError(str(e)) from e

    role = token_payload.get('role')
    patient_id = token_payload.get('sub')

    if role != 'patient':
        raise AuthError('Only patients can access this endpoint')

    patient = Patient.query.filter_by(patient_id=patient_id).first()
    if not patient:
        raise NotFoundError('Patient not found')
    if not patient.active:
        raise AuthError('Account is deactivated')

    prescriptions = []
    for pres in patient.prescriptions:
        prescriptions.append({
            'patient_id': pres.patient_id,
            'medicine_id': pres.medicine_id,
            'medicine_name': pres.medicine.name if pres.medicine else pres.medicine_name,
            'schedule_time': pres.schedule_time.strftime('%H:%M:%S') if pres.schedule_time else None,
            'alzhiemer_level': pres.alzhiemer_level,
            'notes': pres.notes,
        })

    return success_response(
        message='Prescriptions fetched successfully',
        data={
            'patient_id': patient.patient_id,
            'prescriptions': prescriptions,
        },
        status_code=200,
    )


@handle_errors('Fetch doctor patients failed')
def my_patients():
    token = _get_token_from_header()
    if not token:
        raise AuthError('Missing Bearer token')

    try:
        token_payload = decode_token(token)
    except JWTError as e:
        raise AuthError(str(e)) from e

    role = token_payload.get('role')
    doctor_id = token_payload.get('sub')

    if role != 'doctor':
        raise AuthError('Only doctors can access this endpoint')

    doctor = Doctor.query.filter_by(doctor_id=doctor_id).first()
    if not doctor:
        raise NotFoundError('Doctor not found')
    if not doctor.active:
        raise AuthError('Account is deactivated')

    patients = []
    for patient in doctor.patients:
        if not patient.active:
            continue
        patients.append({
            'patient_id': patient.patient_id,
            'name': patient.name,
            'age': patient.age,
            'gender': patient.gender,
            'email': patient.email,
            'phone': patient.phone,
            'chronic_disease': patient.chronic_disease,
            'city': patient.city,
            'address': patient.address,
            'age_category': patient.age_category,
            'hospital_address': patient.hospital_address,
        })

    return success_response(
        message='Doctor patients fetched successfully',
        data={
            'doctor_id': doctor.doctor_id,
            'patients_count': len(patients),
            'patients': patients,
        },
        status_code=200,
    )
