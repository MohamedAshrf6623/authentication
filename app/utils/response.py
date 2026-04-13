from typing import Any

from flask import Response, jsonify


def success_response(data: Any = None, message: str = 'Success', status_code: int = 200) -> tuple[Response, int]:
    payload = {
        'success': True,
        'message': message,
    }
    if data is not None:
        payload['data'] = data
    return jsonify(payload), status_code


def error_response(
    message: str,
    status_code: int = 400,
    code: str | None = None,
    details: dict[str, Any] | None = None,
) -> tuple[Response, int]:
    error_payload = {'message': message}
    if code:
        error_payload['code'] = code
    if details:
        error_payload['details'] = details

    payload = {
        'success': False,
        'message': message,
        'error': error_payload,
    }
    return jsonify(payload), status_code
