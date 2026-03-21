from flask import Blueprint

from app.controllers.gps_controller import receive_gps, get_last_location, get_history


gps_bp = Blueprint('gps', __name__)


@gps_bp.route('/gps', methods=['POST'])
def receive_gps_route():
    return receive_gps()


@gps_bp.route('/gps/last', methods=['GET'])
def get_last_location_route():
    return get_last_location()


@gps_bp.route('/gps/history', methods=['GET'])
def get_history_route():
    return get_history()
