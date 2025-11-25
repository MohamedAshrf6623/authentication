from app import db
from passlib.hash import bcrypt

class Doctor(db.Model):
    __tablename__ = 'Doctors'
    __table_args__ = {'schema': 'dbo'}
    
    doctor_id = db.Column(db.String(50), primary_key=True)
    name = db.Column(db.String(255))
    gender = db.Column(db.String(50))
    specialization = db.Column(db.String(255))
    age = db.Column(db.Integer)
    email = db.Column(db.String(255))
    password = db.Column(db.String(255))
    phone = db.Column(db.String(50))
    city = db.Column(db.String(100))
    clinic_address = db.Column(db.String(255))

    patients = db.relationship('Patient', back_populates='doctor')

    def set_password(self, raw_password: str):
        self.password = bcrypt.hash(raw_password)

    def verify_password(self, raw_password: str) -> bool:
        if not self.password:
            return False
        if self.password.startswith('$2'):
            return bcrypt.verify(raw_password, self.password)
        # legacy plaintext support
        return self.password == raw_password

    @property
    def username(self):
        return self.email or self.name
