from flask import Blueprint
from app.utils.jwt import jwt_required
from app.controllers.chat_controller import ask_text, ask_voice

chat_bp = Blueprint('chat', __name__)


@chat_bp.route('/ask', methods=['POST'])
@jwt_required()
def ask_text_route():
    return ask_text()


@chat_bp.route('/voice', methods=['POST'])
@jwt_required()
def ask_voice_route():
    return ask_voice()
