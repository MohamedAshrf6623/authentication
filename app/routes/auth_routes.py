from flask import Blueprint
from app import limiter
from app.controllers.auth_controller import (
    register,
    register_patient,
    register_doctor,
    register_caregiver,
    login,
    logout,
    forget_password,
    reset_password,
    update_my_password,
)

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/register', methods=['POST'])
@limiter.limit('3 per minute; 15 per hour')
def register_route():
    return register()


@auth_bp.route('/register/patient', methods=['POST'])
@limiter.limit('3 per minute; 15 per hour')
def register_patient_route():
    return register_patient()


@auth_bp.route('/register/doctor', methods=['POST'])
@limiter.limit('3 per minute; 15 per hour')
def register_doctor_route():
    return register_doctor()


@auth_bp.route('/register/caregiver', methods=['POST'])
@limiter.limit('3 per minute; 15 per hour')
def register_caregiver_route():
    return register_caregiver()


@auth_bp.route('/login', methods=['POST'])
@limiter.limit('5 per minute; 25 per hour')
def login_route():
    return login()


@auth_bp.route('/logout', methods=['POST'])
def logout_route():
    return logout()


@auth_bp.route('/forgetpassword', methods=['POST'])
@limiter.limit('2 per minute; 8 per hour')
def forget_password_route():
    return forget_password()


@auth_bp.route('/resetpassword', methods=['POST'])
@limiter.limit('5 per minute; 15 per hour')
def reset_password_route():
    return reset_password()


@auth_bp.route('/updatemypassword', methods=['PATCH', 'POST'])
@limiter.limit('5 per minute; 20 per hour')
def update_my_password_route():
    return update_my_password()
