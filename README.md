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
RATE_LIMIT_PER_HOUR=100 per hour
RATELIMIT_STORAGE_URI=memory://
SMTP_USER=your_gmail@gmail.com
SMTP_PASSWORD=your_gmail_app_password
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
EMAIL_FROM=your_gmail@gmail.com
```
Notes:
- For a local instance use `(local)` or `localhost` or `localhost\\SQLEXPRESS`.
- For Windows Integrated Authentication (Trusted Connection) use:
  `mssql+pyodbc://@SERVER_NAME/DB_NAME?driver=ODBC+Driver+17+for+SQL+Server&trusted_connection=yes`
- For Gmail SMTP, use an App Password (not your account password) and enable 2-Step Verification.
- `RATE_LIMIT_PER_HOUR` applies globally per IP address (default: `100 per hour`).
- `RATELIMIT_STORAGE_URI` controls limiter storage (default: `memory://`).

## 4. Run the server
```powershell
python run.py
```
Server will listen on: http://127.0.0.1:5000

## 5. Rate Limits (Per IP)
The following limits are currently applied on routes:

### 5.1 Auth endpoints
- `POST /auth/login` → `5 per minute; 25 per hour`
- `POST /auth/register` → `3 per minute; 15 per hour`
- `POST /auth/register/patient` → `3 per minute; 15 per hour`
- `POST /auth/register/doctor` → `3 per minute; 15 per hour`
- `POST /auth/register/caregiver` → `3 per minute; 15 per hour`
- `POST /auth/forgetpassword` → `2 per minute; 8 per hour`
- `POST /auth/resetpassword` → `5 per minute; 15 per hour`
- `PATCH/POST /auth/updatemypassword` → `5 per minute; 20 per hour`

## 6. Auth Endpoints (JWT)
Access token is issued on registration or login. Expiry can be configured using `JWT_EXP_MINUTES` in `.env` (default 60 minutes).

### 6.1 Register
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

### 6.2 Login
`POST /auth/login`
Body:
```json
{ "email": "ahmed@example.com", "password": "secret" }
```
Response:
```json
{ "token": "<JWT>", "patient": { ... all patient data ... } }
```

### 6.3 Current user profile
`GET /auth/me`
Headers:

### 6.4 Logout (token revocation)
`POST /auth/logout`
Headers:
`Authorization: Bearer <JWT>`
Adds the token to an in-memory blacklist (for production consider Redis or database persistence).

### 6.5 Forgot password
`POST /auth/forget_password`
Body:
```json
{
  "email": "ahmed@example.com",
  "role": "patient"
}
```
Notes:
- `role` is optional (`patient`, `doctor`, `caregiver`).
- If the same email exists in multiple roles, `role` becomes required.

### 6.6 Reset password
`POST /auth/reset_password`
Body:
```json
{
  "token": "<token-from-email>",
  "password": "newSecret123",
  "confirm_password": "newSecret123"
}
```
Behavior:
- Checks token validity and expiry.
- Updates password and `password_changed_at`.
- Clears reset token fields.
- Issues a fresh JWT.

### 6.7 Token lifetime
Set in `.env`:
```
JWT_EXP_MINUTES=120
```
To set lifetime to 2 hours.

## 7. Create an initial patient (Python REPL)
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

## 8. Migrations (Alembic / Flask-Migrate)
After defining all models you can run:
```powershell
flask --app run.py db init
flask --app run.py db migrate -m "Initial tables"
flask --app run.py db upgrade
```

## 9. Next steps / roadmap
- Add Refresh Token flow.
- Persist revoked tokens list in Redis/DB.
- Rate limiting & structured logging.
- Unit tests for all routes.

## 10. Security notes
- Never store raw passwords; we hash with `passlib` (bcrypt).
- Use a strong separate `JWT_SECRET` distinct from `SECRET_KEY`.
- Do not log JWTs.
- In production use a WSGI server (gunicorn) behind Nginx.
- Security libraries in use:
  - `Flask-Talisman` for security headers (CSP/HSTS/secure cookies).
  - `Flask-SQLAlchemy` for safe ORM access and query parameterization.
  - `Pydantic` for strict JSON payload validation (returns 422 on schema errors).

## 11. Enhancements added
The following improvements were added during this setup:

### 11.1 Dependencies
- Added `Flask-Limiter`, `Flask-Talisman`, `Flask-SQLAlchemy`, and `Pydantic`.

### 11.2 Rate limiting
- Global default limit per IP via `RATE_LIMIT_PER_HOUR`.
- Per-route limits for auth endpoints (see section 5).
- Rate limit errors return JSON with status `429` and code `RATE_LIMIT_EXCEEDED`.

### 11.3 Security headers (Talisman)
- Enabled `Flask-Talisman` with development-friendly settings (no HTTPS redirect).

### 11.4 Request validation (Pydantic)
- JSON payloads for auth, profile updates, and chat now validate strictly.
- Validation errors return HTTP `422` with Pydantic error details.

Good luck 🚀
