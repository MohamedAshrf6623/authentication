from app import db
import bcrypt
from datetime import datetime

class Doctor(db.Model):
    __tablename__ = 'Doctors'
    __table_args__ = {'schema': 'dbo'}
    
    doctor_id = db.Column(db.String(50), primary_key=True)
    name = db.Column(db.String(255))
    gender = db.Column(db.String(50))
    specialization = db.Column(db.String(255))
    age = db.Column(db.Integer)
    email = db.Column(db.String(255))
    password = db.Column(db.String(500))  # hashed password (bcrypt is 60+ chars)
    password_changed_at = db.Column(db.DateTime, nullable=True)
    password_reset_token = db.Column(db.String(255), nullable=True)
    password_reset_expires = db.Column(db.DateTime, nullable=True)
    phone = db.Column(db.String(50))
    city = db.Column(db.String(100))
    clinic_address = db.Column(db.String(255))

    patients = db.relationship('Patient', back_populates='doctor')

    def set_password(self, raw_password: str):
        """Hash and store password. bcrypt has 72-byte limit."""
        # Ensure we're working with bytes, limit to 72 bytes
        if isinstance(raw_password, str):
            raw_password = raw_password.encode('utf-8')
        raw_password = raw_password[:72]
        # Hash password
        hashed = bcrypt.hashpw(raw_password, bcrypt.gensalt())
        self.password = hashed.decode('utf-8')
        self.password_changed_at = datetime.utcnow()

    def verify_password(self, raw_password: str) -> bool:
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
