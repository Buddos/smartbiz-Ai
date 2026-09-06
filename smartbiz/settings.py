import os
import shutil
import urllib.parse
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("SECRET_KEY", "django-insecure-change-this-in-production")
DEBUG = os.environ.get("DEBUG", "True").lower() in ("true", "1", "t")

ALLOWED_HOSTS = [
    "127.0.0.1",
    "localhost",
    ".vercel.app",
    ".now.sh",
]

if allowed_hosts_env := os.environ.get("ALLOWED_HOSTS"):
    ALLOWED_HOSTS.extend(
        [host.strip() for host in allowed_hosts_env.split(",") if host.strip() and host.strip() not in ALLOWED_HOSTS]
    )

CSRF_TRUSTED_ORIGINS = [
    "https://*.vercel.app",
    "https://*.now.sh",
]

if csrf_origins_env := os.environ.get("CSRF_TRUSTED_ORIGINS"):
    CSRF_TRUSTED_ORIGINS.extend(
        [origin.strip() for origin in csrf_origins_env.split(",") if origin.strip() and origin.strip() not in CSRF_TRUSTED_ORIGINS]
    )

# Required behind Vercel reverse proxy for HTTPS detection
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")


INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "rest_framework",
    "accounts.apps.AccountsConfig",
    "businesses.apps.BusinessesConfig",
    "products.apps.ProductsConfig",
    "customers.apps.CustomersConfig",
    "sales.apps.SalesConfig",
    "expenses.apps.ExpensesConfig",
    "inventory.apps.InventoryConfig",
    "analytics.apps.AnalyticsConfig",
    "ai_engine.apps.AiEngineConfig",
    "reports.apps.ReportsConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "accounts.middleware.BusinessMiddleware",
]

ROOT_URLCONF = "smartbiz.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "smartbiz.context_processors.business_context",
            ],
        },
    },
]

WSGI_APPLICATION = "smartbiz.wsgi.application"
ASGI_APPLICATION = "smartbiz.asgi.application"

database_url = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL")

if database_url:
    url = urllib.parse.urlparse(database_url)
    query_params = urllib.parse.parse_qs(url.query)
    options = {}
    if "sslmode" in query_params:
        options["sslmode"] = query_params["sslmode"][0]
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": url.path.lstrip("/"),
            "USER": url.username or "",
            "PASSWORD": url.password or "",
            "HOST": url.hostname or "",
            "PORT": str(url.port or 5432),
            "OPTIONS": options,
        }
    }
else:
    # SQLite configuration:
    # On Vercel serverless functions, the deployment directory (/var/task) is read-only.
    # SQLite needs a writable location (/tmp) to open connections and write lock/journal files.
    sqlite_db_path = BASE_DIR / "db.sqlite3"
    is_vercel = bool(os.environ.get("VERCEL")) or str(BASE_DIR).startswith("/var/task")

    if is_vercel:
        tmp_db_path = Path("/tmp/db.sqlite3")
        if sqlite_db_path.exists() and not tmp_db_path.exists():
            try:
                shutil.copy2(sqlite_db_path, tmp_db_path)
            except Exception:
                pass
        sqlite_db_path = tmp_db_path

    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": sqlite_db_path,
        }
    }


AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
    {"NAME": "accounts.validators.PasswordComplexityValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Africa/Nairobi"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
AI_ENGINE_EVENT_PIPELINE = True

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "accounts:login"

REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.BasicAuthentication",
    ],
}
