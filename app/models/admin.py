from datetime import datetime

import bcrypt

from app import db


class Admin(db.Model):
    __tablename__ = 'Admins'
    __table_args__ = {'schema': 'dbo'}

    admin_id = db.Column(db.String(50), primary_key=True)
    name = db.Column(db.String(255))
    email = db.Column(db.String(255), nullable=False, unique=True)
    password = db.Column(db.String(500), nullable=False)
    password_changed_at = db.Column(db.DateTime, nullable=True)
    password_reset_token = db.Column(db.String(255), nullable=True)
    password_reset_expires = db.Column(db.DateTime, nullable=True)
    active = db.Column(db.Boolean, nullable=False, default=True)

    def set_password(self, raw_password: str):
        if isinstance(raw_password, str):
            raw_password = raw_password.encode('utf-8')
        raw_password = raw_password[:72]
        hashed = bcrypt.hashpw(raw_password, bcrypt.gensalt())
        self.password = hashed.decode('utf-8')
        self.password_changed_at = datetime.utcnow()

    def verify_password(self, raw_password: str) -> bool:
        if not self.password:
            return False
        if isinstance(raw_password, str):
            raw_password = raw_password.encode('utf-8')
        raw_password = raw_password[:72]
        if isinstance(self.password, str):
            stored_hash = self.password.encode('utf-8')
        else:
            stored_hash = self.password
        try:
            return bcrypt.checkpw(raw_password, stored_hash)
        except Exception:
            return self.password == raw_password

    @property
    def username(self):
        return self.email or self.name