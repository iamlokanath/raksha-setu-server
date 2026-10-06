import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def load_env_file() -> None:
    path = BASE_DIR / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


load_env_file()

SECRET_KEY = os.environ.get("SECRET_KEY") or "dev-only-not-for-production"
DEBUG = os.environ.get("DJANGO_DEBUG", "false").lower() == "true"
ALLOWED_HOSTS = [host.strip() for host in os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if host.strip()]
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite+pysqlite:///raksha.sqlite3")
ACCESS_TOKEN_TTL_SECONDS = int(os.environ.get("ACCESS_TOKEN_TTL_SECONDS", "900"))
REFRESH_TOKEN_TTL_SECONDS = int(os.environ.get("REFRESH_TOKEN_TTL_SECONDS", "604800"))
CORS_ALLOWED_ORIGINS = [item.strip() for item in os.environ.get("CORS_ALLOWED_ORIGINS", "http://localhost:3000").split(",") if item.strip()]
SEED_PASSWORD = os.environ.get("SEED_PASSWORD", "")
SMS_PROVIDER = os.environ.get("SMS_PROVIDER", "")
TELEPHONY_PROVIDER = os.environ.get("TELEPHONY_PROVIDER", "")

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.staticfiles",
    "raksha",
]
MIDDLEWARE = [
    "common.middleware.RequestIdMiddleware",
    "common.middleware.CorsMiddleware",
    "common.middleware.DatabaseMiddleware",
    "common.middleware.AuthMiddleware",
]
ROOT_URLCONF = "raksha.urls"
WSGI_APPLICATION = "raksha.wsgi.application"
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": str(BASE_DIR / ".django.sqlite3"),
    }
}
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
APPEND_SLASH = False
PUBLIC_API_PATHS = {
    "/api/v1/auth/login",
    "/api/v1/auth/refresh",
    "/api/v1/docs",
    "/api/v1/schema",
}
