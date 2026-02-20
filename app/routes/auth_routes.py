from flask import Blueprint
from app.controllers.auth_controller import (
    register,
    register_patient,
    register_doctor,
    register_caregiver,
    login,
    me,
    logout,
)

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/register', methods=['POST'])
def register_route():
    return register()


@auth_bp.route('/register/patient', methods=['POST'])
def register_patient_route():
    return register_patient()


@auth_bp.route('/register/doctor', methods=['POST'])
def register_doctor_route():
    return register_doctor()


@auth_bp.route('/register/caregiver', methods=['POST'])
def register_caregiver_route():
    return register_caregiver()


@auth_bp.route('/login', methods=['POST'])
def login_route():
    return login()


@auth_bp.route('/me', methods=['GET'])
def me_route():
    return me()


@auth_bp.route('/logout', methods=['POST'])
def logout_route():
    return logout()
