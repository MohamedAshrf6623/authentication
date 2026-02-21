from flask import Blueprint
from app.controllers.user_controller import (
    me,
    updateme,
)

user_bp = Blueprint('user', __name__)


@user_bp.route('/me', methods=['GET'])
def me_route():
    return me()


@user_bp.route('/updateme', methods=['PATCH', 'POST'])
def updateme_route():
    return updateme()
