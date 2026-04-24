from datetime import datetime

from app import db


class GameScore(db.Model):
    __tablename__ = 'GameScores'
    __table_args__ = {'schema': 'dbo'}

    game_score_id = db.Column(db.String(50), primary_key=True)
    doctor_id = db.Column(db.String(50), db.ForeignKey('dbo.Doctors.doctor_id'), nullable=False)
    patient_id = db.Column(db.String(50), db.ForeignKey('dbo.Patients.patient_id'), nullable=False)
    score = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    doctor = db.relationship('Doctor', back_populates='game_scores')
    patient = db.relationship('Patient', back_populates='game_scores')
