from app import db

class CareGiver(db.Model):
    __tablename__ = 'Care_givers'
    __table_args__ = {'schema': 'dbo'}
    
    care_giver_id = db.Column(db.String(50), primary_key=True)
    name = db.Column(db.String(255))
    relation = db.Column(db.String(100))
    email = db.Column(db.String(255))
    password = db.Column(db.String(255))
    phone = db.Column(db.String(50))
    city = db.Column(db.String(100))
    address = db.Column(db.String(255))

    patients = db.relationship('Patient', back_populates='care_giver')
