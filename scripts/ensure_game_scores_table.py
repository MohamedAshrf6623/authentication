from sqlalchemy import text

from app import create_app, db


CREATE_TABLE_SQL = """
IF OBJECT_ID('dbo.GameScores', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.GameScores (
        game_score_id VARCHAR(50) NOT NULL PRIMARY KEY,
        doctor_id VARCHAR(50) NOT NULL,
        patient_id VARCHAR(50) NOT NULL,
        score INT NOT NULL,
        created_at DATETIME2 NOT NULL DEFAULT GETDATE(),
        CONSTRAINT FK_GameScores_Doctors FOREIGN KEY (doctor_id) REFERENCES dbo.Doctors(doctor_id),
        CONSTRAINT FK_GameScores_Patients FOREIGN KEY (patient_id) REFERENCES dbo.Patients(patient_id)
    );
END
"""


def main():
    app = create_app()
    with app.app_context():
        db.session.execute(text(CREATE_TABLE_SQL))
        db.session.commit()
        print('GameScores table is ready.')


if __name__ == '__main__':
    main()
