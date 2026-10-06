# Raksha Setu Server

District-level emergency shelter coordination API.

Behaviour is specified in [documents/README.md](documents/README.md). Application routes are class-based REST under `/api/v1/`. State changes publish domain events after commit.

## Run locally

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
copy .env.example .env
```

Set `SECRET_KEY` and `SEED_PASSWORD` in `.env`. For PostgreSQL, start the database and point `DATABASE_URL` at it:

```powershell
docker compose up -d
.\.venv\Scripts\python -m alembic upgrade head
.\.venv\Scripts\python manage.py seed
.\.venv\Scripts\python manage.py runserver 8000
```

Swagger UI is at `http://localhost:8000/ap  i/v1/docs`.

Tests:

```powershell
.\.venv\Scripts\python -m pytest
```

Open decisions (shortage thresholds, capacity thresholds, priority weights, SMS provider) stay empty until an administrator saves approved configuration. The API will not invent those values.

