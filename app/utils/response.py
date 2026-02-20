from flask import jsonify


def success_response(data=None, message: str = 'Success', status_code: int = 200):
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
    details: dict | None = None,
):
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
