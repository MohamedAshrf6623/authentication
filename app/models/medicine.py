from app import db

class Medicine(db.Model):
    __tablename__ = 'Medicines'
    __table_args__ = {'schema': 'dbo'}
    
    medicine_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255))
    class_ = db.Column('class', db.String(100))
    indication = db.Column(db.String(255))
    dose = db.Column(db.String(100))
    warnings = db.Column(db.String(255))

    prescriptions = db.relationship('MPrescription', back_populates='medicine')
