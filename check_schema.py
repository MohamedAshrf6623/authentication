from app import create_app, db

app = create_app()
with app.app_context():
    # Get column info for M_Prescriptions
    result = db.session.execute(db.text("""
        SELECT COLUMN_NAME, DATA_TYPE 
        FROM INFORMATION_SCHEMA.COLUMNS 
        WHERE TABLE_SCHEMA = 'dbo' 
        AND TABLE_NAME = 'M_Prescriptions'
        ORDER BY ORDINAL_POSITION
    """))
    
    print("M_Prescriptions table schema:")
    for row in result:
        print(f"  {row.COLUMN_NAME}: {row.DATA_TYPE}")
    
    print("\n" + "="*50 + "\n")
    
    # Get column info for Medicines
    result2 = db.session.execute(db.text("""
        SELECT COLUMN_NAME, DATA_TYPE 
        FROM INFORMATION_SCHEMA.COLUMNS 
        WHERE TABLE_SCHEMA = 'dbo' 
        AND TABLE_NAME = 'Medicines'
        ORDER BY ORDINAL_POSITION
    """))
    
    print("Medicines table schema:")
    for row in result2:
        print(f"  {row.COLUMN_NAME}: {row.DATA_TYPE}")
