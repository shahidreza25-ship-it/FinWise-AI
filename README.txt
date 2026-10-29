FINWISE AI PUBLIC — MULTI-USER STARTER

LOCAL RUN (Mac):
1. Open Terminal in this folder.
2. python3 -m venv .venv
3. source .venv/bin/activate
4. pip install -r requirements.txt
5. python app.py
6. Open http://127.0.0.1:5000

PUBLIC DEPLOY:
1. Upload the contents of this folder to a GitHub repository.
2. In Render, create a Web Service from that repository.
3. Render should use requirements.txt and Procfile; start command: gunicorn app:app.
4. Set SECRET_KEY to a long random secret (Render can generate one).
5. Configure persistent disk/database before storing real user financial data.

INCLUDED:
- Individual signup/login/logout; each account sees only its own data.
- Budget, income/expense tracking, transaction deletion.
- Category charts and rule-based personal finance advisor.
- Savings goals with Add Money and delete.
- CSV transaction import (review imported records).
- Responsive layout for phones and desktop.
- Render deployment configuration.

IMPORTANT LIMITATIONS / SAFETY:
- This is a starter project, not a bank or regulated financial service.
- It does NOT automatically read PhonePe, Google Pay, SMS, notifications, or bank accounts.
- Live bank-data sync requires a legitimate authorized provider, user consent, provider/bank eligibility, and appropriate security/compliance work.
- CSV import currently maps amount and optional type/category/date columns. Review records after importing; duplicate prevention is not implemented.
- SQLite is fine for local demo/testing. For a public multi-user production service, use managed PostgreSQL or properly configured persistent storage, HTTPS, backups, rate limiting, CSRF protection, password reset, and security review before real financial data.
- Change SECRET_KEY in production; never commit passwords or secrets.
