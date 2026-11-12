import os

from celery.schedules import crontab
from dotenv import load_dotenv

from .base import *

load_dotenv()

def env_bool(name, default=False):
    return os.getenv(name, str(default)).lower() in {"1", "true", "yes", "on"}

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", os.getenv("SECRET_KEY"))
DEBUG = os.getenv("DJANGO_DEBUG", "False").lower() in {"1", "true", "yes", "on"}
ROOT_URLCONF = "project.urls"
AUTH_USER_MODEL = "account.User"
WSGI_APPLICATION = "project.wsgi.application"
ASGI_APPLICATION = "project.asgi.application"

ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv("ALLOWED_HOSTS", "localhost").split(",")
    if host.strip()
]
CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
]
CORS_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",")
    if origin.strip()
]

CORS_ALLOW_ALL_ORIGINS = env_bool("CORS_ALLOW", False)
CORS_ALLOW_CREDENTIALS = True
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
DEFAULT_FROM_EMAIL = os.getenv(
    "DEFAULT_FROM_EMAIL",
    os.getenv("RESEND_FROM_EMAIL", "onboarding@resend.dev"),
)
RESEND_FROM_EMAIL = DEFAULT_FROM_EMAIL
CELERY_BROKER_URL = os.getenv(
    "CELERY_BROKER_URL",
    "amqp://harvest:harvest@rabbitmq:5672//",
)
CELERY_TASK_DEFAULT_QUEUE = "harvesting"
CELERY_TASK_ROUTES = {
    "apps.harvesting.process_harvest_step": {"queue": "harvesting"},
}
CELERY_TASK_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_IGNORE_RESULT = True
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_ENABLE_UTC = True
CELERY_TIMEZONE = "UTC"
CELERY_BEAT_SCHEDULE = {
    "harvesting-run-due-every-5m": {
        "task": "apps.scheduler.tasks.dispatch_http_job",
        "schedule": crontab(minute="*/5"),
        "kwargs": {"job": "harvesting_due"},
    },
    "platforms-check-links-every-4h": {
        "task": "apps.scheduler.tasks.dispatch_http_job",
        "schedule": crontab(minute=0, hour="*/4"),
        "kwargs": {"job": "check_links"},
    },
    "platforms-check-failed-links-every-15m": {
        "task": "apps.scheduler.tasks.dispatch_http_job",
        "schedule": crontab(minute="*/15"),
        "kwargs": {"job": "check_failed_links"},
    },
}
SCHEDULER_API_URL = os.getenv("SCHEDULER_API_URL", "http://backend:8000")
SCHEDULER_API_TOKEN = os.getenv("SCHEDULER_API_TOKEN", "")
SCHEDULER_SERVICE_USER_ID = os.getenv("SCHEDULER_SERVICE_USER_ID", "")
LINK_CHECK_BATCH_SIZE = max(1, int(os.getenv("LINK_CHECK_BATCH_SIZE", "50")))
LINK_FAILURE_FRONTEND_URL = os.getenv("LINK_FAILURE_FRONTEND_URL", "")
FRONTEND_LOGIN_URL = os.getenv(
    "FRONTEND_LOGIN_URL",
    "https://repositorio-biblioteca-frontend.vercel.app/admin/login",
)
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_AGE = 15 * 60
# La renovación por inactividad la hace ThrottledSessionRenewalMiddleware
# (apps.core.middleware) como máximo cada SESSION_RENEWAL_INTERVAL segundos,
# en lugar de escribir la sesión en la base en cada petición.
SESSION_SAVE_EVERY_REQUEST = False
SESSION_RENEWAL_INTERVAL = min(
    max(0, int(os.getenv("SESSION_RENEWAL_INTERVAL", "60"))),
    SESSION_COOKIE_AGE,
)
CSRF_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_SAMESITE = "None" if not DEBUG else "Lax"
CSRF_COOKIE_SAMESITE = SESSION_COOKIE_SAMESITE

if os.getenv("DJANGO_TESTING", "").lower() in {"1", "true", "yes", "on"}:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "test.sqlite3",
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("POSTGRES_DB", os.getenv("DATABASE_NAME")),
            "USER": os.getenv("POSTGRES_USER", os.getenv("DATABASE_USER")),
            "PASSWORD": os.getenv(
                "POSTGRES_PASSWORD",
                os.getenv("DATABASE_PASSWORD"),
            ),
            "HOST": os.getenv(
                "POSTGRES_HOST",
                os.getenv("DATABASE_HOST", "db"),
            ),
            "PORT": os.getenv(
                "POSTGRES_PORT",
                os.getenv("DATABASE_PORT", "5432"),
            ),
            "OPTIONS": {"sslmode": os.getenv("DATABASE_SSLMODE", "require")},
            # El pool sustituye a las conexiones persistentes; Django no admite
            # ambos mecanismos a la vez.
            "CONN_MAX_AGE": 0,
        }
    }

    # Pool de conexiones de psycopg (Django >= 5.1). Solo se activa en el
    # servicio web: Celery prefork cierra el pool al terminar cada tarea, por
    # lo que en worker/beat añadiría aperturas de conexión en lugar de evitarlas.
    if env_bool("DATABASE_POOL", False):
        _pool_min_size = max(1, int(os.getenv("DATABASE_POOL_MIN_SIZE", "2")))
        DATABASES["default"]["OPTIONS"]["pool"] = {
            "min_size": _pool_min_size,
            "max_size": max(
                _pool_min_size,
                int(os.getenv("DATABASE_POOL_MAX_SIZE", "4")),
            ),
            # Segundos que una petición espera una conexión libre.
            "timeout": float(os.getenv("DATABASE_POOL_TIMEOUT", "10")),
            # Cierra conexiones ociosas antes de que el proveedor las corte.
            "max_idle": float(os.getenv("DATABASE_POOL_MAX_IDLE", "300")),
        }

# --- Almacenamiento S3 (RustFS) ---
S3_ENDPOINT = os.getenv("S3_ENDPOINT", "")
S3_PUBLIC_ENDPOINT = os.getenv("S3_PUBLIC_ENDPOINT", S3_ENDPOINT)
S3_BUCKET = os.getenv("S3_BUCKET", "imagenes")
S3_REGION = os.getenv("S3_REGION", "us-east-1")
S3_ACCESS_KEY = os.getenv(
    "S3_ACCESS_KEY",
    os.getenv("RUSTFS_ACCESS_KEY", ""),
)
S3_SECRET_KEY = os.getenv(
    "S3_SECRET_KEY",
    os.getenv("RUSTFS_SECRET_KEY", ""),
)
S3_MAX_IMAGE_SIZE = max(
    1,
    int(os.getenv("S3_MAX_IMAGE_SIZE", str(5 * 1024 * 1024))),
)
S3_ALLOWED_IMAGE_CONTENT_TYPES = tuple(
    item.strip()
    for item in os.getenv(
        "S3_ALLOWED_IMAGE_CONTENT_TYPES",
        "image/jpeg,image/png,image/gif,image/webp",
    ).split(",")
    if item.strip()
)

SPECTACULAR_SETTINGS = {
    "TITLE": "API Sistema de Revistas",
    "DESCRIPTION": "Documentación de los endpoints del sistema.",
    "VERSION": "1.0.0",
}

LANGUAGE_CODE = "es-mx"
TIME_ZONE = "America/Mexico_City"
