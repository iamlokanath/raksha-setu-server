# Raksha Setu Server

District-level emergency shelter coordination API. Routes are class-based REST under `/api/v1/`.

Open a terminal in this folder (`raksha-setu-server`) before you run the commands below. Use PowerShell.

## Start the application

Use this every time, after the one-time setup.

```powershell
.\.venv\Scripts\python manage.py runserver 8000
```

Leave that window open. The API is at http://127.0.0.1:8000. API docs are at http://127.0.0.1:8000/api/v1/docs.

Stop it with Ctrl+C in that window.

Start this server before the UI. The UI calls http://localhost:8000.

## One-time setup

You need Python 3.11 or newer.

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
copy .env.example .env
```

Open `.env` and set these three lines. This uses a local SQLite file, so Docker is not required:

```text
DATABASE_URL=sqlite+pysqlite:///raksha.sqlite3
SECRET_KEY=local-dev-secret-key-32-characters-min
SEED_PASSWORD=choose-a-password
```

`SEED_PASSWORD` must be at least 8 characters. That value is the password for every seeded account.

Create the pilot district, shelters, and users once:

```powershell
.\.venv\Scripts\python manage.py seed
```

When that prints that the pilot data is ready, go back to **Start the application**. Running `seed` again is safe; it will not create a second copy.

## Sign-in accounts

Use these usernames in the UI. The password is the `SEED_PASSWORD` you set in `.env`. On the login screen, pick the role that matches the account.

| Username | Role on the login screen |
| --- | --- |
| `district` | District Officer |
| `block` | Block Officer |
| `warden_a` | Shelter Warden (Shelter A) |
| `warden_b` | Shelter Warden (Shelter B) |
| `volunteer` | Volunteer / Support |
| `admin` | District Officer |

`admin` is a district officer who can also register shelters, manage users, and save warning configuration.

## Tests

```powershell
.\.venv\Scripts\python -m pytest
```

## Optional: PostgreSQL

Use this only if you want PostgreSQL instead of the SQLite file. Docker must be running. In `.env`, set `DATABASE_URL`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, and `POSTGRES_DB` to the same database name and password, then:

```powershell
docker compose up -d
.\.venv\Scripts\python -m alembic upgrade head
.\.venv\Scripts\python manage.py seed
.\.venv\Scripts\python manage.py runserver 8000
```

Shortage thresholds, capacity thresholds, and priority weights stay empty until an administrator saves them. The API does not invent those values.
