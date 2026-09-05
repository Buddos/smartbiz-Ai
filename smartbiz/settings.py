import os
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

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
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
