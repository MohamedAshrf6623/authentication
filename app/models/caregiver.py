from app import db
import bcrypt

class CareGiver(db.Model):
    __tablename__ = 'Care_givers'
    __table_args__ = {'schema': 'dbo'}
    
    care_giver_id = db.Column(db.String(50), primary_key=True)
    name = db.Column(db.String(255))
    relation = db.Column(db.String(100))
    email = db.Column(db.String(255))
    password = db.Column(db.String(500))  # hashed password (bcrypt is 60+ chars)
    phone = db.Column(db.String(50))
    city = db.Column(db.String(100))
    address = db.Column(db.String(255))

    patients = db.relationship('Patient', back_populates='care_giver')

    def set_password(self, raw_password: str):
        """Hash and store password. bcrypt has 72-byte limit."""
        # Ensure we're working with bytes, limit to 72 bytes
        if isinstance(raw_password, str):
            raw_password = raw_password.encode('utf-8')
        raw_password = raw_password[:72]
        # Hash password
        hashed = bcrypt.hashpw(raw_password, bcrypt.gensalt())
        self.password = hashed.decode('utf-8')

    def verify_password(self, raw_password: str) -> bool:
        """Check password. Supports both hashed (bcrypt) and plaintext legacy passwords."""
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
            return self.password == raw_password

    @property
    def username(self):
        return self.email or self.name

