from datetime import datetime

from app import db


class SystemLog(db.Model):
    __tablename__ = 'SystemLogs'
    __table_args__ = {'schema': 'dbo'}

    log_id = db.Column(db.String(50), primary_key=True)
    event_type = db.Column(db.String(100), nullable=False)
    message = db.Column(db.String(500), nullable=False)
    actor_role = db.Column(db.String(50), nullable=True)
    actor_id = db.Column(db.String(50), nullable=True)
    target_role = db.Column(db.String(50), nullable=True)
    target_id = db.Column(db.String(50), nullable=True)
    target_email = db.Column(db.String(255), nullable=True)
    details = db.Column(db.Text, nullable=True)
    source_ip = db.Column(db.String(100), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)