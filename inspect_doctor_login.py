from app import create_app, db
import sqlalchemy as sa

def inspect(email: str):
    app = create_app()
    with app.app_context():
        result = db.session.execute(sa.text("SELECT doctor_id, name, email, password FROM dbo.Doctors WHERE LOWER(email)=:e"), {'e': email.lower()})
        rows = result.fetchall()
        if not rows:
            print(f"No doctor found with email={email}")
        else:
            for r in rows:
                print(f"doctor_id={r.doctor_id} name={r.name} email={r.email} password={r.password}")

if __name__ == '__main__':
    inspect('saratahat1@gmail.com')
