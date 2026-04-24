from flask import request
from sqlalchemy import func
from datetime import datetime
from uuid import uuid4

from app import db
from app.models.patient import Patient
from app.models.caregiver import CareGiver
from app.models.doctor import Doctor
from app.models.medicine import Medicine
from app.models.prescription import MPrescription
from app.models.game_score import GameScore
from app.models.todo import ToDo
from app.utils.jwt import decode_token, JWTError, revoke_token
from app.utils.error_handler import handle_errors, AppError, AuthError, ValidationError, NotFoundError
from app.utils.response import success_response

# --- التعديل: استيراد الموديلات والدوال الجديدة ---
from app.utils.validation import (
    validate_payload,
    UpdateMePayload,
    AddPrescriptionPayload,
    AddGameScorePayload,
    RegisterDeviceTokenPayload,
    AddTodoPayload,
    UpdateTodoPayload,
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


def _parse_due_date(due_date_value):
    if due_date_value is None:
        return None
    value = str(due_date_value).strip()
    if not value:
        return None
    try:
        normalized = value.replace('Z', '+00:00')
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is not None:
            parsed = parsed.replace(tzinfo=None)
        return parsed
    except ValueError as exc:
        raise ValidationError('Invalid due_date format. Use ISO-8601 datetime') from exc


def _todo_to_dict(todo: ToDo):
    return {
        'todo_id': todo.todo_id,
        'patient_id': todo.patient_id,
        'title': todo.title,
        'description': todo.description,
        'due_date': todo.due_date.isoformat() if todo.due_date else None,
        'is_done': todo.is_done,
        'created_by_role': todo.created_by_role,
        'created_by_id': todo.created_by_id,
        'created_at': todo.created_at.isoformat() if todo.created_at else None,
        'updated_at': todo.updated_at.isoformat() if todo.updated_at else None,
    }


def _game_score_to_dict(game_score: GameScore):
    return {
        'game_score_id': game_score.game_score_id,
        'doctor_id': game_score.doctor_id,
        'patient_id': game_score.patient_id,
        'score': game_score.score,
        'created_at': game_score.created_at.isoformat() if game_score.created_at else None,
    }


def _resolve_token_identity():
    token = _get_token_from_header()
    if not token:
        raise AuthError('Missing Bearer token')
    try:
        payload = decode_token(token)
    except JWTError as e:
        raise AuthError(str(e)) from e

    role = payload.get('role')
    subject = payload.get('sub')
    if role not in ['patient', 'doctor', 'caregiver'] or not subject:
        raise AuthError('Invalid token payload')
    return role, subject


def _doctor_patient_guard(doctor_id: str, patient_id: str):
    doctor = Doctor.query.filter_by(doctor_id=doctor_id).first()
    if not doctor or not doctor.active:
        raise AuthError('Doctor account issues')

    patient = Patient.query.filter_by(patient_id=patient_id).first()
    if not patient or not patient.active:
        raise NotFoundError('Patient not found/active')

    if patient.doctor_id != doctor_id:
        raise AuthError('Unauthorized for this patient')

    return patient


def _caregiver_patient_guard(caregiver_id: str, patient_id: str):
    caregiver = CareGiver.query.filter_by(care_giver_id=caregiver_id).first()
    if not caregiver or not caregiver.active:
        raise AuthError('Caregiver account issues')

    patient = Patient.query.filter_by(patient_id=patient_id).first()
    if not patient or not patient.active:
        raise NotFoundError('Patient not found/active')

    if patient.care_giver_id != caregiver_id:
        raise AuthError('Unauthorized for this patient')

    return patient

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
    data = validate_payload(UpdateMePayload, request.get_json(silent=True) or {})
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
    payload = validate_payload(AddPrescriptionPayload, request.get_json(silent=True) or {})
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
@handle_errors('Add game score failed')
def add_game_score():
    payload = validate_payload(AddGameScorePayload, request.get_json(silent=True) or {})
    token = _get_token_from_header()
    if not token:
        raise AuthError('Missing Bearer token')
    try:
        token_payload = decode_token(token)
    except JWTError as e:
        raise AuthError(str(e)) from e

    role = token_payload.get('role')
    doctor_id_from_token = token_payload.get('sub')
    if role != 'doctor' or not doctor_id_from_token:
        raise AuthError('Only doctors can add game scores')
    if doctor_id_from_token != payload['doctor_id']:
        raise AuthError('doctor_id does not match authenticated doctor')

    patient = _doctor_patient_guard(payload['doctor_id'], payload['patient_id'])

    game_score = GameScore(
        game_score_id=str(uuid4()),
        doctor_id=payload['doctor_id'],
        patient_id=patient.patient_id,
        score=payload['score'],
    )
    db.session.add(game_score)
    db.session.commit()

    return success_response(
        message='Game score added successfully',
        data=_game_score_to_dict(game_score),
        status_code=201,
    )


@handle_errors('Fetch patient game scores failed')
def get_patient_game_scores(patient_id: str):
    patient = Patient.query.filter_by(patient_id=patient_id).first()
    if not patient or not patient.active:
        raise NotFoundError('Patient not found/active')

    scores = (
        GameScore.query
        .filter_by(patient_id=patient.patient_id)
        .order_by(GameScore.created_at.desc())
        .all()
    )

    return success_response(
        data={
            'patient_id': patient.patient_id,
            'scores': [_game_score_to_dict(score) for score in scores],
        }
    )


@handle_errors('Register device token failed')
def register_device_token():
    payload = validate_payload(RegisterDeviceTokenPayload, request.get_json(silent=True) or {})
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


@handle_errors('Add todo failed')
def add_todo():
    payload = validate_payload(AddTodoPayload, request.get_json(silent=True) or {})
    role, subject = _resolve_token_identity()

    if role not in ['patient', 'caregiver']:
        raise AuthError('Only patient or caregiver can add todo')

    title = (payload.get('title') or '').strip()
    if not title:
        raise ValidationError('title is required')

    if role == 'patient':
        patient_id = subject
        requested_patient_id = payload.get('patient_id')
        if requested_patient_id and requested_patient_id != patient_id:
            raise AuthError('Patient can only add todo for self')
        patient = Patient.query.filter_by(patient_id=patient_id).first()
        if not patient or not patient.active:
            raise NotFoundError('Patient not found/active')
    else:
        patient_id = payload.get('patient_id')
        if not patient_id:
            raise ValidationError('patient_id is required for caregiver')
        patient = _caregiver_patient_guard(subject, patient_id)

    todo = ToDo(
        todo_id=str(uuid4()),
        patient_id=patient.patient_id,
        title=title,
        description=payload.get('description'),
        due_date=_parse_due_date(payload.get('due_date')),
        is_done=False,
        created_by_role=role,
        created_by_id=subject,
    )
    db.session.add(todo)
    db.session.commit()

    return success_response(
        message='Todo added successfully',
        data=_todo_to_dict(todo),
        status_code=201,
    )


@handle_errors('Fetch patient todos failed')
def get_patient_todos(patient_id: str):
    role, subject = _resolve_token_identity()
    if role == 'patient':
        if subject != patient_id:
            raise AuthError('Patient can only view own todos')
        patient = Patient.query.filter_by(patient_id=patient_id).first()
        if not patient or not patient.active:
            raise NotFoundError('Patient not found/active')
    elif role == 'caregiver':
        patient = _caregiver_patient_guard(subject, patient_id)
    else:
        raise AuthError('Only patient or caregiver can view todos')

    todos = (
        ToDo.query
        .filter_by(patient_id=patient.patient_id)
        .order_by(ToDo.created_at.desc())
        .all()
    )

    return success_response(
        data={
            'patient_id': patient.patient_id,
            'todos': [_todo_to_dict(todo) for todo in todos],
        }
    )


@handle_errors('Update todo failed')
def update_todo(todo_id: str):
    payload = validate_payload(UpdateTodoPayload, request.get_json(silent=True) or {})
    role, subject = _resolve_token_identity()
    if role not in ['patient', 'caregiver']:
        raise AuthError('Only patient or caregiver can update todo')

    todo = ToDo.query.filter_by(todo_id=todo_id).first()
    if not todo:
        raise NotFoundError('Todo not found')

    if role == 'patient':
        if todo.patient_id != subject:
            raise AuthError('Patient can only update own todos')
    else:
        _caregiver_patient_guard(subject, todo.patient_id)

    if all(value is None for value in payload.values()):
        raise ValidationError('At least one field is required to update')

    if payload.get('title') is not None:
        title = str(payload.get('title')).strip()
        if not title:
            raise ValidationError('title cannot be empty')
        todo.title = title

    if payload.get('description') is not None:
        todo.description = payload.get('description')

    if payload.get('due_date') is not None:
        todo.due_date = _parse_due_date(payload.get('due_date'))

    if payload.get('is_done') is not None:
        todo.is_done = bool(payload.get('is_done'))

    db.session.commit()
    return success_response(message='Todo updated successfully', data=_todo_to_dict(todo))


@handle_errors('Delete todo failed')
def delete_todo(todo_id: str):
    role, subject = _resolve_token_identity()
    if role not in ['patient', 'caregiver']:
        raise AuthError('Access denied')

    todo = ToDo.query.filter_by(todo_id=todo_id).first()
    if not todo:
        raise NotFoundError('Todo not found')

    if role == 'patient':
        if todo.patient_id != subject:
            raise AuthError('Unauthorized to delete this todo')
    else:
        _caregiver_patient_guard(subject, todo.patient_id)

    db.session.delete(todo)
    db.session.commit()
    return success_response(message='Todo deleted successfully')
