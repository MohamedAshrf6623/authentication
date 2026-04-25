from flask import Blueprint

from app.controllers.admin_controller import (
    create_user,
    list_logs,
    list_users,
    manage_user_account,
    new_patient_logs,
    overview,
    patient_login_logs,
    update_user_email,
)

admin_bp = Blueprint('admin', __name__)


@admin_bp.route('/overview', methods=['GET'])
def overview_route():
    return overview()


@admin_bp.route('/users', methods=['GET'])
def list_all_users_route():
    return list_users()


@admin_bp.route('/users/<string:role>', methods=['GET'])
def list_users_by_role_route(role):
    return list_users(role)


@admin_bp.route('/users/<string:role>', methods=['POST'])
def create_user_route(role):
    return create_user(role)


@admin_bp.route('/users/<string:role>/<string:user_id>/email', methods=['PATCH'])
def update_user_email_route(role, user_id):
    return update_user_email(role, user_id)


@admin_bp.route('/users/<string:role>/<string:user_id>/account-action', methods=['PATCH'])
def manage_user_account_route(role, user_id):
    return manage_user_account(role, user_id)


@admin_bp.route('/logs', methods=['GET'])
def list_logs_route():
    return list_logs()


@admin_bp.route('/logs/patient-logins', methods=['GET'])
def patient_login_logs_route():
    return patient_login_logs()


@admin_bp.route('/logs/new-patients', methods=['GET'])
def new_patient_logs_route():
    return new_patient_logs()