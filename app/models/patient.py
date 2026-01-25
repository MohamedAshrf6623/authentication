from app import db
from passlib.hash import bcrypt

class Patient(db.Model):
    __tablename__ = 'Patients'
    __table_args__ = {'schema': 'dbo'}

    patient_id = db.Column(db.String(50), primary_key=True)  # user_id in your DB
    name = db.Column(db.String(255))
    age = db.Column(db.Integer)
    chronic_disease = db.Column(db.String(255))
    email = db.Column(db.String(255))
    password = db.Column(db.String(255), nullable=False)  # plaintext or hashed
    gender = db.Column(db.String(50))
    phone = db.Column(db.String(50))
    doctor_id = db.Column(db.String(50), db.ForeignKey('dbo.Doctors.doctor_id'))
    care_giver_id = db.Column(db.String(50), db.ForeignKey('dbo.Care_givers.care_giver_id'))
    city = db.Column(db.String(100))
    address = db.Column(db.String(255))
    age_category = db.Column(db.String(100))
    hospital_address = db.Column(db.String(255))

    # Relationships
    doctor = db.relationship('Doctor', back_populates='patients')
    care_giver = db.relationship('CareGiver', back_populates='patients')
    prescriptions = db.relationship('MPrescription', back_populates='patient')

    def set_password(self, raw_password: str):
        """Hash and store password (for new registrations)."""
        self.password = bcrypt.hash(raw_password)

    def verify_password(self, raw_password: str) -> bool:
        """
        Check password. Supports both hashed (bcrypt) and plaintext legacy passwords.
        If plaintext found, upgrades to bcrypt on next login.
        """
        if not self.password:
            return False
        # Try bcrypt verification first
        if self.password.startswith('$2'):  # bcrypt hash starts with $2a$, $2b$, etc.
            return bcrypt.verify(raw_password, self.password)
        # Fallback: plaintext comparison (legacy)
        return self.password == raw_password

    @property
    def username(self):
        return self.email or self.name
