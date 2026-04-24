from flask import Blueprint

from app.controllers.user_controller import (
    add_game_score,
    add_prescription,
    add_todo,
    deleteme,
    get_patient_game_scores,
    get_patient_todos,
    me,
    my_patients,
    my_prescriptions,
    register_device_token,
    update_todo,
    updateme,
    delete_todo,
)

user_bp = Blueprint('user', __name__)


@user_bp.route('/me', methods=['GET'])
def me_route():
    return me()


@user_bp.route('/updateme', methods=['PATCH', 'POST'])
def updateme_route():
    return updateme()


@user_bp.route('/deleteme', methods=['DELETE', 'POST'])
def deleteme_route():
    return deleteme()


@user_bp.route('/prescriptions', methods=['POST'])
def add_prescription_route():
    return add_prescription()


@user_bp.route('/my-prescriptions', methods=['GET'])
def my_prescriptions_route():
    return my_prescriptions()


@user_bp.route('/my-patients', methods=['GET'])
def my_patients_route():
    return my_patients()


@user_bp.route('/games/scores', methods=['POST'])
def add_game_score_route():
    return add_game_score()


@user_bp.route('/games/scores/patient/<string:patient_id>', methods=['GET'])
def get_patient_game_scores_route(patient_id):
    return get_patient_game_scores(patient_id)


@user_bp.route('/device-token', methods=['POST'])
def register_device_token_route():
    return register_device_token()


@user_bp.route('/todos', methods=['POST'])
def add_todo_route():
    return add_todo()


@user_bp.route('/todos/patient/<string:patient_id>', methods=['GET'])
def get_patient_todos_route(patient_id):
    return get_patient_todos(patient_id)


@user_bp.route('/todos/<string:todo_id>', methods=['PATCH'])
def update_todo_route(todo_id):
    return update_todo(todo_id)


@user_bp.route('/todos/<string:todo_id>', methods=['DELETE'])
def delete_todo_route(todo_id):
    return delete_todo(todo_id)
