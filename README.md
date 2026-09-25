# Vegili

Vegili is a social posting and private chat application. This repository contains a FastAPI + PostgreSQL MVP with an HTML/CSS/JavaScript interface.

## Features
- Email registration with one-time verification code and unique Vegili ID
- Secure password hashing and signed HTTP-only session cookie
- Feed posts, likes and comments
- Email-based user search and contact requests
- Contact list and private WebSocket chat
- Profile name/email/password settings and logout
- Responsive three-tab app shell: Feed, Chat, Settings

## Run locally
1. Use Python 3.11+ and PostgreSQL, or set `DATABASE_URL` to a PostgreSQL connection string.
2. Create a virtual environment and install dependencies: `pip install -r requirements.txt`
3. Copy `.env.example` to `.env` and set `DATABASE_URL` and a long random `SECRET_KEY`.
4. Start: `uvicorn app.main:app --reload`
5. Open http://127.0.0.1:8000

If SMTP settings are not configured, the development OTP is printed to the server log. Configure SMTP before public deployment. Do not use this fallback in production.

## Render
The included `render.yaml` describes a web service and managed PostgreSQL database. Add `SECRET_KEY`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` and `APP_BASE_URL` as environment variables in Render. Set `EMAIL_OTP_DEV_MODE=false` once SMTP is configured. The app creates tables on startup for this MVP; use versioned migrations before production scale.

## Important MVP limits
This is a starter implementation, not a security-audited production service. Rate limiting, abuse reporting/moderation, password reset, image uploads, persistent WebSocket fan-out across multiple instances, migrations and comprehensive tests should be added before public launch. Email codes are stored in process memory in this first version, so use a single instance until replaced with a shared store.
