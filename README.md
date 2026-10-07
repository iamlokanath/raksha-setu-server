# Raksha Setu Server

District-level emergency shelter coordination API. Routes are class-based REST under `/api/v1/`.

## Quick Start

### Prerequisites
- Python 3.11+
- Git

Open a terminal in this folder (`raksha-setu-server`). The commands below are for Windows Command Prompt, the same form as `venv\Scripts\activate`.

### 1. Setup Environment
```bat
python -m venv .venv
.venv\Scripts\activate
```

The prompt starts with `(.venv)` when activation worked. Run the remaining commands in that same window.

### 2. Install Dependencies
```bat
pip install -r requirements.txt
```

### 3. Setup Environment File
```bat
copy .env.example .env
```

Open `.env` and set these three lines. This uses a local SQLite file, so Docker is not required:

```text
DATABASE_URL=sqlite+pysqlite:///raksha.sqlite3
SECRET_KEY=local-dev-secret-key-32-characters-min
SEED_PASSWORD=choose-a-password
```

`SEED_PASSWORD` must be at least 8 characters. That value is the password for every seeded account.

### 4. Setup Database
```bat
alembic current
alembic upgrade head
alembic current
```

`alembic current` is the status check. Before the upgrade it may be empty. After `alembic upgrade head`, `current` should match `alembic heads`.

Create the pilot district, shelters, and users once:

```bat
python manage.py seed
```

Running `seed` again is safe. It will not create a second copy.

### 5. Start Server
```bat
python manage.py runserver 8000
```

Leave this window open. Stop the server with Ctrl+C.

### 6. Access API
- **API**: http://127.0.0.1:8000
- **Docs**: http://127.0.0.1:8000/api/v1/docs

Start this server before the UI. The UI calls http://localhost:8000.

## Regular Use

Do this every time you want the API running. Steps 1 to 4 above are already done.

```bat
.venv\Scripts\activate
alembic current
alembic upgrade head
alembic current
python manage.py runserver 8000
```

In a second window, confirm the server is answering. A status code of `200` means it is up.

```bat
curl http://127.0.0.1:8000/api/v1/docs
```

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

## Database

```bat
alembic current
alembic heads
alembic upgrade head
```

`alembic current` prints the revision already applied. `alembic heads` prints the latest revision in this repo.

## Testing

```bat
pytest
```

## Optional: PostgreSQL

Use this only if you want PostgreSQL instead of the SQLite file. Docker must be running. In `.env`, set `DATABASE_URL`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, and `POSTGRES_DB` to the same database name and password, then:

```bat
docker compose up -d
alembic upgrade head
python manage.py seed
python manage.py runserver 8000
```

Shortage thresholds, capacity thresholds, and priority weights stay empty until an administrator saves them. The API does not invent those values.
