from flask import Blueprint
from app import limiter
from app.controllers.user_controller import (
    me,
    updateme,
    deleteme,
    add_prescription,
    my_prescriptions,
    my_patients,
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
