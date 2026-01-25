from flask import Blueprint, request, jsonify
from app.models.patient import Patient
from app.models.caregiver import CareGiver
from app.models.prescription import MPrescription
from app.models.medicine import Medicine
from app.models.doctor import Doctor
from app import db
from app.utils.jwt import create_access_token, decode_token, JWTError, revoke_token
from sqlalchemy import or_, func
import re
from uuid import uuid4

auth_bp = Blueprint('auth', __name__)

def _patient_to_dict(patient: Patient):
    presc_list = []
    for pres in patient.prescriptions:
        # Convert time object to string for JSON serialization
        schedule_time_str = pres.schedule_time.strftime('%H:%M:%S') if pres.schedule_time else None
        
        presc_list.append({
            'medicine_id': pres.medicine_id,
            'medicine_name': pres.medicine.name if pres.medicine else pres.medicine_name,
            'schedule_time': schedule_time_str,
            'alzhiemer_level': pres.alzhiemer_level,  # Note: Database has misspelling
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

def _issue_token(subject: str, role: str):
    return create_access_token(subject, role=role)


def _normalize_email(email: str):
    return email.strip().lower()


def _missing_fields(data: dict, required: list[str]):
    return [f for f in required if not data.get(f)]


def _validate_email(email: str):
    return re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email)


def _register_patient(data: dict):
    required = ['name', 'email', 'password', 'doctor_id', 'care_giver_id']
    missing = _missing_fields(data, required)
    if missing:
        return jsonify({'error': f'Missing required fields: {", ".join(missing)}'}), 400

    email = _normalize_email(data['email'])
    if not _validate_email(email):
        return jsonify({'error': 'Invalid email format'}), 400

    # Check if patient email already exists
    existing = Patient.query.filter(func.lower(Patient.email) == email).first()
    if existing:
        return jsonify({'error': 'Email already registered'}), 409

    # Verify doctor exists
    doctor = Doctor.query.filter_by(doctor_id=data['doctor_id']).first()
    if not doctor:
        return jsonify({'error': f'Doctor with id {data["doctor_id"]} does not exist'}), 400

    # Verify caregiver exists
    caregiver = CareGiver.query.filter_by(care_giver_id=data['care_giver_id']).first()
    if not caregiver:
        return jsonify({'error': f'CareGiver with id {data["care_giver_id"]} does not exist'}), 400

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
        age_category=data.get('age_category') or 'Unknown',  # Default value if not provided
        hospital_address=data.get('hospital_address') or 'Not specified',  # Default value if not provided
        doctor_id=data['doctor_id'],
        care_giver_id=data['care_giver_id'],
    )
    patient.set_password(data['password'])
    db.session.add(patient)
    db.session.commit()

    token = _issue_token(str(patient.patient_id), 'patient')
    return jsonify({'token': token, 'patient': _patient_to_dict(patient)}), 201


def _register_doctor(data: dict):
    required = ['name', 'email', 'password']
    missing = _missing_fields(data, required)
    if missing:
        return jsonify({'error': f'Missing fields: {", ".join(missing)}'}), 400

    email = _normalize_email(data['email'])
    if not _validate_email(email):
        return jsonify({'error': 'Invalid email format'}), 400

    existing = Doctor.query.filter(func.lower(Doctor.email) == email).first()
    if existing:
        return jsonify({'error': 'Email already registered'}), 409

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

    token = _issue_token(str(doctor.doctor_id), 'doctor')
    return jsonify({'token': token, 'doctor': _doctor_to_dict(doctor)}), 201


def _register_caregiver(data: dict):
    required = ['name', 'email', 'password']
    missing = _missing_fields(data, required)
    if missing:
        return jsonify({'error': f'Missing fields: {", ".join(missing)}'}), 400

    email = _normalize_email(data['email'])
    if not _validate_email(email):
        return jsonify({'error': 'Invalid email format'}), 400

    existing = CareGiver.query.filter(func.lower(CareGiver.email) == email).first()
    if existing:
        return jsonify({'error': 'Email already registered'}), 409

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

    token = _issue_token(str(caregiver.care_giver_id), 'caregiver')
    return jsonify({'token': token, 'caregiver': _caregiver_to_dict(caregiver)}), 201

@auth_bp.route('/register', methods=['POST'])
def register():
    # Backward compatible patient signup
    data = request.get_json() or {}
    return _register_patient(data)


@auth_bp.route('/register/patient', methods=['POST'])
def register_patient():
    return _register_patient(request.get_json() or {})


@auth_bp.route('/register/doctor', methods=['POST'])
def register_doctor():
    return _register_doctor(request.get_json() or {})


@auth_bp.route('/register/caregiver', methods=['POST'])
def register_caregiver():
    return _register_caregiver(request.get_json() or {})

@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    role = (data.get('role') or '').strip().lower()  # optional: 'patient', 'doctor', or 'caregiver'
    identifier = (data.get('email') or data.get('username') or data.get('name') or '').strip()
    password = data.get('password')
    if not identifier or not password:
        return jsonify({'error': 'email/username and password are required'}), 400

    # Normalize for case-insensitive email match
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
        # auto-detect: try patient first then doctor then caregiver
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
        return jsonify({'error': 'invalid credentials'}), 401

    if user_role == 'patient':
        token = create_access_token(str(user_obj.patient_id), role=user_role)
        return jsonify({'token': token, 'role': user_role, 'patient': _patient_to_dict(user_obj)}), 200
    elif user_role == 'doctor':
        token = create_access_token(str(user_obj.doctor_id), role=user_role)
        return jsonify({'token': token, 'role': user_role, 'doctor': _doctor_to_dict(user_obj)}), 200
    else:  # caregiver
        token = create_access_token(str(user_obj.care_giver_id), role=user_role)
        return jsonify({'token': token, 'role': user_role, 'caregiver': _caregiver_to_dict(user_obj)}), 200

@auth_bp.route('/me', methods=['GET'])
def me():
    token = _get_token_from_header()
    if not token:
        return jsonify({'error': 'Missing Bearer token'}), 401
    try:
        payload = decode_token(token)
    except JWTError as e:
        return jsonify({'error': str(e)}), 401
    role = payload.get('role')
    sub = payload.get('sub')
    
    if role == 'doctor':
        doctor = Doctor.query.filter_by(doctor_id=sub).first()
        if not doctor:
            return jsonify({'error': 'Doctor not found'}), 404
        return jsonify(_doctor_to_dict(doctor)), 200
    elif role == 'caregiver':
        caregiver = CareGiver.query.filter_by(care_giver_id=sub).first()
        if not caregiver:
            return jsonify({'error': 'CareGiver not found'}), 404
        return jsonify(_caregiver_to_dict(caregiver)), 200
    else:  # default patient
        patient = Patient.query.filter_by(patient_id=sub).first()
        if not patient:
            return jsonify({'error': 'Patient not found'}), 404
        return jsonify(_patient_to_dict(patient)), 200

@auth_bp.route('/logout', methods=['POST'])
def logout():
    token = _get_token_from_header()
    if not token:
        return jsonify({'error': 'Missing Bearer token'}), 401
    try:
        decode_token(token)  # validate before revoking
    except JWTError as e:
        return jsonify({'error': str(e)}), 401
    revoke_token(token)
    return jsonify({'message': 'Logged out'}), 200

def _get_token_from_header():
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        return auth_header.split(' ', 1)[1]
    return None
