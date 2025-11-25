# Flask Backend for Patient Authentication (JWT)

This project is a Flask backend for registering patients, authenticating them, and issuing JWT access tokens with an expiry to access protected data.

## 1. Prerequisites
- Python 3.11 or later
- ODBC Driver 17 (or 18) for SQL Server (install from Microsoft site)
- SQL Server instance (database already created in SSMS)

## 2. Create virtual environment & install dependencies (PowerShell)
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 3. Database connection configuration
Edit `.env` based on the example:
```env
DATABASE_URL=mssql+pyodbc://USERNAME:PASSWORD@SERVER_NAME/DB_NAME?driver=ODBC+Driver+17+for+SQL+Server
SECRET_KEY=CHANGE_ME_TO_A_SECURE_VALUE
```
Notes:
- For a local instance use `(local)` or `localhost` or `localhost\\SQLEXPRESS`.
- For Windows Integrated Authentication (Trusted Connection) use:
  `mssql+pyodbc://@SERVER_NAME/DB_NAME?driver=ODBC+Driver+17+for+SQL+Server&trusted_connection=yes`

## 4. Run the server
```powershell
python run.py
```
Server will listen on: http://127.0.0.1:5000

## 5. Auth Endpoints (JWT)
Access token is issued on registration or login. Expiry can be configured using `JWT_EXP_MINUTES` in `.env` (default 60 minutes).

### 5.1 Register
`POST /auth/register`
Body:
```json
{
  "name": "Ahmed Ali",
  "email": "ahmed@example.com",
  "password": "secret"
}
```
Response:
```json
{ "token": "<JWT>", "patient": { "patient_id": 1, "name": "Ahmed Ali", "email": "ahmed@example.com" } }
```

### 5.2 Login
`POST /auth/login`
Body:
```json
{ "email": "ahmed@example.com", "password": "secret" }
```
Response:
```json
{ "token": "<JWT>", "patient": { ... بيانات المريض كاملة ... } }
```

### 5.3 Current user profile
`GET /auth/me`
Headers:
`Authorization: Bearer <JWT>`
Response: بيانات المريض + الوصفات + الطبيب + الـ Care Giver.

### 5.4 Logout (token revocation)
`POST /auth/logout`
Headers:
`Authorization: Bearer <JWT>`
Adds the token to an in-memory blacklist (for production consider Redis or database persistence).

### 5.5 Token lifetime
Set in `.env`:
```
JWT_EXP_MINUTES=120
```
To set lifetime to 2 hours.

## 6. Create an initial patient (Python REPL)
```powershell
python
```
Inside Python REPL:
```python
from app import create_app, db
from app.models.patient import Patient
app = create_app()
ctx = app.app_context(); ctx.push()

p = Patient(username='patient1', full_name='Ahmed Ali', email='ahmed@example.com')
p.set_password('secret')

db.session.add(p)
db.session.commit()
```

## 7. Migrations (Alembic / Flask-Migrate)
After defining all models you can run:
```powershell
flask --app run.py db init
flask --app run.py db migrate -m "Initial tables"
flask --app run.py db upgrade
```

## 8. Next steps / roadmap
- Add Refresh Token flow.
- Persist revoked tokens list in Redis/DB.
- Rate limiting & structured logging.
- Unit tests for all routes.

## 9. Security notes
- Never store raw passwords; we hash with `passlib` (bcrypt).
- Use a strong separate `JWT_SECRET` distinct from `SECRET_KEY`.
- Do not log JWTs.
- In production use a WSGI server (gunicorn) behind Nginx.

Good luck 🚀
