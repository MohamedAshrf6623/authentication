from datetime import datetime

from app import db


class ToDo(db.Model):
    __tablename__ = 'To_Dos'
    __table_args__ = {'schema': 'dbo'}

    todo_id = db.Column(db.String(50), primary_key=True)
    patient_id = db.Column(db.String(50), db.ForeignKey('dbo.Patients.patient_id'), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.String(1000), nullable=True)
    due_date = db.Column(db.DateTime, nullable=True)
    is_done = db.Column(db.Boolean, nullable=False, default=False)
    created_by_role = db.Column(db.String(20), nullable=False)
    created_by_id = db.Column(db.String(50), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    patient = db.relationship('Patient', backref=db.backref('todos', lazy=True))
