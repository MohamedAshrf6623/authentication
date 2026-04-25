import json
import uuid

from flask import request

from app import db
from app.models.system_log import SystemLog


def record_system_log(
    event_type: str,
    message: str,
    actor_role: str | None = None,
    actor_id: str | None = None,
    target_role: str | None = None,
    target_id: str | None = None,
    target_email: str | None = None,
    details: dict | str | None = None,
):
    if isinstance(details, dict):
        details_value = json.dumps(details, ensure_ascii=True, default=str)
    else:
        details_value = details

    log = SystemLog(
        log_id=str(uuid.uuid4()),
        event_type=event_type,
        message=message,
        actor_role=actor_role,
        actor_id=actor_id,
        target_role=target_role,
        target_id=target_id,
        target_email=target_email,
        details=details_value,
        source_ip=request.headers.get('X-Forwarded-For', request.remote_addr),
    )
    db.session.add(log)
    return log