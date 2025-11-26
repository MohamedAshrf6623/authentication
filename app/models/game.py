from app import db

class Game(db.Model):
    __tablename__ = 'Games'
    __table_args__ = {'schema': 'dbo'}
    
    game_id = db.Column(db.String(50), primary_key=True)
    name = db.Column(db.String(255))
    description = db.Column(db.Text)
