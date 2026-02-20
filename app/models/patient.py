from app import db
import bcrypt
from datetime import datetime

class Patient(db.Model):
    __tablename__ = 'Patients'
    __table_args__ = {'schema': 'dbo'}

    patient_id = db.Column(db.String(50), primary_key=True)  # user_id in your DB
    name = db.Column(db.String(255))
    age = db.Column(db.Integer)
    chronic_disease = db.Column(db.String(255))
    email = db.Column(db.String(255))
    password = db.Column(db.String(500), nullable=False)  # hashed password (bcrypt is 60+ chars)
    password_changed_at = db.Column(db.DateTime, nullable=True)
    password_reset_token = db.Column(db.String(255), nullable=True)
    password_reset_expires = db.Column(db.DateTime, nullable=True)
    gender = db.Column(db.String(50))
    phone = db.Column(db.String(50))
    doctor_id = db.Column(db.String(50), db.ForeignKey('dbo.Doctors.doctor_id'), nullable=False)
    care_giver_id = db.Column(db.String(50), db.ForeignKey('dbo.Care_givers.care_giver_id'), nullable=False)
    city = db.Column(db.String(100))
    address = db.Column(db.String(255))
    age_category = db.Column(db.String(100))
    hospital_address = db.Column(db.String(255))

    # Relationships
    doctor = db.relationship('Doctor', back_populates='patients')
    care_giver = db.relationship('CareGiver', back_populates='patients')
    prescriptions = db.relationship('MPrescription', back_populates='patient')

    def set_password(self, raw_password: str):
        """Hash and store password (for new registrations). bcrypt has 72-byte limit."""
        # Ensure we're working with bytes, limit to 72 bytes
        if isinstance(raw_password, str):
            raw_password = raw_password.encode('utf-8')
        raw_password = raw_password[:72]
        # Hash password
        hashed = bcrypt.hashpw(raw_password, bcrypt.gensalt())
        self.password = hashed.decode('utf-8')
        self.password_changed_at = datetime.utcnow()

    def verify_password(self, raw_password: str) -> bool:
        """
        Check password. Supports both hashed (bcrypt) and plaintext legacy passwords.
        If plaintext found, upgrades to bcrypt on next login.
        bcrypt has 72-byte limit.
        """
        if not self.password:
            return False
        # Ensure we're working with bytes, limit to 72 bytes
        if isinstance(raw_password, str):
            raw_password = raw_password.encode('utf-8')
        raw_password = raw_password[:72]
        if isinstance(self.password, str):
            stored_hash = self.password.encode('utf-8')
        else:
            stored_hash = self.password
        try:
            return bcrypt.checkpw(raw_password, stored_hash)
        except:
            # legacy plaintext support
            return self.password == raw_password

    @property
    def username(self):
        return self.email or self.name
