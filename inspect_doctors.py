from app import create_app, db
import sqlalchemy as sa

app = create_app()
with app.app_context():
    r = db.session.execute(sa.text("SELECT COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='Doctors' ORDER BY ORDINAL_POSITION"))
    print('Doctors schema:')
    for row in r:
        print(f"  {row.COLUMN_NAME}: {row.DATA_TYPE}")
