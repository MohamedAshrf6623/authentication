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

# --- التعديل: استيراد الموديلات والدوال الجديدة ---
from app.utils.validation import (
    validate_payload,
    UpdateMePayload,
    AddPrescriptionPayload,
    RegisterDeviceTokenPayload
)
from app.utils.sns_helper import register_device_to_sns, send_push_notification
# ---------------------------------------------

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
        'patients': [{'patient_id': p.patient_id, 'name': p.name, 'age': p.age, 'gender': p.gender, 'email': p.email} for p in caregiver.patients]
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
        'patients': [{'patient_id': p.patient_id, 'name': p.name, 'age': p.age, 'gender': p.gender, 'email': p.email} for p in doctor.patients]
    }

def _public_user_payload(user_obj, role: str):
    if role == 'patient': return {'patient': _patient_to_dict(user_obj)}
    if role == 'doctor': return {'doctor': _doctor_to_dict(user_obj)}
    return {'caregiver': _caregiver_to_dict(user_obj)}

def _get_token_from_header():
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '): return auth_header.split(' ', 1)[1]
    data = request.get_json(silent=True) or {}
    body_token = data.get('token') or data.get('access_token') or data.get('bearer_token')
    if body_token:
        token_str = str(body_token).strip()
        if token_str.startswith('Bearer '): return token_str.split(' ', 1)[1]
        return token_str
    return None

def _parse_schedule_time(schedule_time_value: str):
    value = str(schedule_time_value or '').strip()
    if not value: raise ValidationError('schedule_time is required in HH:MM or HH:MM:SS format')
    for fmt in ('%H:%M:%S', '%H:%M'):
        try: return datetime.strptime(value, fmt).time()
        except ValueError: continue
    raise ValidationError('Invalid schedule_time format. Use HH:MM or HH:MM:SS')

@handle_errors('Fetch profile failed')
def me():
    token = _get_token_from_header()
    if not token: raise AuthError('Missing Bearer token')
    try: payload = decode_token(token)
    except JWTError as e: raise AuthError(str(e)) from e
    role, sub = payload.get('role'), payload.get('sub')
    if role == 'doctor':
        user = Doctor.query.filter_by(doctor_id=sub).first()
        if not user: raise NotFoundError('Doctor not found')
        return success_response(data=_doctor_to_dict(user))
    if role == 'caregiver':
        user = CareGiver.query.filter_by(care_giver_id=sub).first()
        if not user: raise NotFoundError('CareGiver not found')
        return success_response(data=_caregiver_to_dict(user))
    user = Patient.query.filter_by(patient_id=sub).first()
    if not user: raise NotFoundError('Patient not found')
    return success_response(data=_patient_to_dict(user))

@handle_errors('Update profile failed')
def updateme():
    data = validate_payload(UpdateMePayload, request.get_json() or {})
    if data.get('password'): raise ValidationError('Use /auth/updatemypassword for password updates.')
    token = _get_token_from_header()
    if not token: raise AuthError('Missing Bearer token')
    try: payload = decode_token(token)
    except JWTError as e: raise AuthError(str(e)) from e
    role, sub = payload.get('role'), payload.get('sub')
    if role == 'patient':
        allowed = ['name', 'email', 'age', 'gender', 'phone', 'chronic_disease', 'city', 'address', 'hospital_address']
        user = Patient.query.filter_by(patient_id=sub).first()
    elif role == 'doctor':
        allowed = ['name', 'email', 'age', 'gender', 'phone', 'city', 'specialization', 'clinic_address']
        user = Doctor.query.filter_by(doctor_id=sub).first()
    else:
        allowed = ['name', 'email', 'phone', 'city', 'address', 'relation']
        user = CareGiver.query.filter_by(care_giver_id=sub).first()
    if not user: raise NotFoundError('User not found')
    for k, v in data.items():
        if k in allowed and v is not None: setattr(user, k, v)
    db.session.commit()
    return success_response(data=_public_user_payload(user, role))

@handle_errors('Delete profile failed')
def deleteme():
    token = _get_token_from_header()
    if not token: raise AuthError('Missing Bearer token')
    try: payload = decode_token(token)
    except JWTError as e: raise AuthError(str(e)) from e
    role, sub = payload.get('role'), payload.get('sub')
    if role == 'patient': user = Patient.query.filter_by(patient_id=sub).first()
    elif role == 'doctor': user = Doctor.query.filter_by(doctor_id=sub).first()
    else: user = CareGiver.query.filter_by(care_giver_id=sub).first()
    if not user: raise NotFoundError('User not found')
    user.active = False
    db.session.commit()
    revoke_token(token)
    return success_response(message='Account deactivated')

@handle_errors('Add prescription failed')
def add_prescription():
    payload = validate_payload(AddPrescriptionPayload, request.get_json() or {})
    token = _get_token_from_header()
    if not token: raise AuthError('Missing Bearer token')
    try: token_payload = decode_token(token)
    except JWTError as e: raise AuthError(str(e)) from e
    role, doctor_id = token_payload.get('role'), token_payload.get('sub')
    if role != 'doctor': raise AuthError('Only doctors can add prescriptions')
    doctor = Doctor.query.filter_by(doctor_id=doctor_id).first()
    if not doctor or not doctor.active: raise AuthError('Doctor account issues')
    patient = Patient.query.filter_by(patient_id=payload['patient_id']).first()
    if not patient or not patient.active: raise NotFoundError('Patient not found/active')
    if patient.doctor_id != doctor_id: raise AuthError('Unauthorized for this patient')
    medicine = Medicine.query.filter_by(medicine_id=payload['medicine_id']).first()
    if not medicine: raise NotFoundError('Medicine not found')
    schedule_time = _parse_schedule_time(payload['schedule_time'])
    existing = MPrescription.query.filter_by(patient_id=payload['patient_id'], medicine_id=payload['medicine_id']).first()
    if existing:
        existing.medicine_name, existing.schedule_time = medicine.name, schedule_time
        existing.alzhiemer_level, existing.notes = payload.get('alzhiemer_level'), payload.get('notes')
        msg, prescription_obj = 'Prescription updated successfully', existing
    else:
        prescription_obj = MPrescription(patient_id=payload['patient_id'], medicine_id=payload['medicine_id'], medicine_name=medicine.name, schedule_time=schedule_time, alzhiemer_level=payload.get('alzhiemer_level'), notes=payload.get('notes'))
        db.session.add(prescription_obj)
        msg = 'Prescription added successfully'
    db.session.commit()

    # --- التعديل: إرسال الإشعار للمريض ---
    if patient.sns_endpoint_arn:
        title = "وصفة طبية جديدة 💊"
        body = f"أضاف طبيبك دواء ({medicine.name}) بموعد {schedule_time.strftime('%H:%M')}. ملاحظات: {payload.get('notes', 'لا يوجد')}"
        send_push_notification(patient.sns_endpoint_arn, title, body)
    # ----------------------------------

    return success_response(message=msg, data={'patient_id': prescription_obj.patient_id, 'medicine_id': prescription_obj.medicine_id, 'medicine_name': prescription_obj.medicine_name, 'schedule_time': prescription_obj.schedule_time.strftime('%H:%M:%S'), 'notes': prescription_obj.notes}, status_code=201 if msg == 'Prescription added successfully' else 200)

@handle_errors('Fetch prescriptions failed')
def my_prescriptions():
    token = _get_token_from_header()
    if not token: raise AuthError('Missing Bearer token')
    try: tp = decode_token(token)
    except JWTError as e: raise AuthError(str(e)) from e
    if tp.get('role') != 'patient': raise AuthError('Access denied')
    patient = Patient.query.filter_by(patient_id=tp.get('sub')).first()
    if not patient: raise NotFoundError('Patient not found')
    prescs = [{'medicine_name': p.medicine_name, 'schedule_time': p.schedule_time.strftime('%H:%M:%S'), 'notes': p.notes} for p in patient.prescriptions]
    return success_response(data={'prescriptions': prescs})

@handle_errors('Fetch doctor patients failed')
def my_patients():
    token = _get_token_from_header()
    if not token: raise AuthError('Missing Bearer token')
    try: tp = decode_token(token)
    except JWTError as e: raise AuthError(str(e)) from e
    if tp.get('role') != 'doctor': raise AuthError('Access denied')
    doctor = Doctor.query.filter_by(doctor_id=tp.get('sub')).first()
    patients = [{'patient_id': p.patient_id, 'name': p.name, 'email': p.email} for p in doctor.patients if p.active]
    return success_response(data={'patients': patients})

# --- التعديل: دالة تسجيل توكن الموبايل ---
@handle_errors('Register device token failed')
def register_device_token():
    payload = validate_payload(RegisterDeviceTokenPayload, request.get_json() or {})
    token = _get_token_from_header()
    if not token: raise AuthError('Missing Bearer token')
    try: tp = decode_token(token)
    except JWTError as e: raise AuthError(str(e)) from e
    if tp.get('role') != 'patient': raise AuthError('Only patients can register tokens')
    patient = Patient.query.filter_by(patient_id=tp.get('sub')).first()
    if not patient: raise NotFoundError('Patient not found')

    # تسجيل في AWS SNS
    arn = register_device_to_sns(payload['fcm_token'])
    if arn:
        patient.fcm_token = payload['fcm_token']
        patient.sns_endpoint_arn = arn
        db.session.commit()
        return success_response(message='Device registered for notifications')
    raise AppError('Failed to register device with AWS', status_code=500)
