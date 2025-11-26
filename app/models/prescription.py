from app import db
from sqlalchemy import Time

class MPrescription(db.Model):
    __tablename__ = 'M_Prescriptions'
    __table_args__ = {'schema': 'dbo'}
    
    # Composite primary key
    patient_id = db.Column(db.String(50), db.ForeignKey('dbo.Patients.patient_id'), primary_key=True, nullable=False)
    medicine_id = db.Column(db.Integer, db.ForeignKey('dbo.Medicines.medicine_id'), primary_key=True, nullable=False)
    medicine_name = db.Column(db.String(255))
    schedule_time = db.Column(Time)  # TIME type in database
    alzhiemer_level = db.Column(db.String(100))  # Note: Database has misspelling "alzhiemer"
    notes = db.Column(db.String(255))

    patient = db.relationship('Patient', back_populates='prescriptions')
    medicine = db.relationship('Medicine', back_populates='prescriptions')
