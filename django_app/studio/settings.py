import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
# OneDrive syncing can corrupt a live SQLite file, so on Windows keep it in local app data, not the app folder.
LEGACY_DATA_DIR = BASE_DIR / "data"
_default_data_dir = (
    Path(os.environ["LOCALAPPDATA"]) / "SilverBirdStudio"
    if os.name == "nt" and os.environ.get("LOCALAPPDATA") else LEGACY_DATA_DIR
)
DATA_DIR = Path(os.environ.get("STUDIO_DATA_DIR", _default_data_dir))
DATA_DIR.mkdir(parents=True, exist_ok=True)


def _load_secret_key() -> str:
    if key := os.environ.get("DJANGO_SECRET_KEY"):
        return key
    key_file = DATA_DIR / "secret_key.txt"
    if not key_file.exists():
        key_file.write_text(secrets.token_urlsafe(50))
    return key_file.read_text().strip()


SECRET_KEY = _load_secret_key()
DEBUG = os.environ.get("DJANGO_DEBUG") == "1"
# Home-network app reached by whatever IP the laptop gets; set a comma-separated list to restrict.
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "*").split(",")
STUDIO_LAN_IP = os.environ.get("STUDIO_LAN_IP", "")
STUDIO_HOSTNAME = os.environ.get("STUDIO_HOSTNAME", "")
# Off by default: anyone on the home Wi-Fi gets straight in. Set STUDIO_REQUIRE_LOGIN=1 to require a password.
REQUIRE_LOGIN = os.environ.get("STUDIO_REQUIRE_LOGIN") == "1"

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "whitenoise.runserver_nostatic",
    "django.contrib.staticfiles",
    "django_htmx",
    "tracker",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.auth.middleware.LoginRequiredMiddleware" if REQUIRE_LOGIN else "tracker.middleware.AutoLoginMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "tracker.middleware.DailyBackupMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
]

ROOT_URLCONF = "studio.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "tracker.middleware.login_settings",
                "tracker.undo.offer",
            ],
        },
    },
]

WSGI_APPLICATION = "studio.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": DATA_DIR / "studio.sqlite3",
        "OPTIONS": {
            "transaction_mode": "IMMEDIATE",
            "timeout": 20,
            # WAL lets pages keep reading while a purchase is being saved.
            "init_command": "PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;",
        },
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "tracker:dashboard"
LOGOUT_REDIRECT_URL = "login"
SESSION_COOKIE_AGE = 60 * 60 * 24 * 90

LANGUAGE_CODE = "en-gb"
TIME_ZONE = "Europe/London"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
WHITENOISE_USE_FINDERS = True
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "studio.storage.StaticStorage"},
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

BACKUP_DIR = DATA_DIR / "backups"
# Point this at a OneDrive/Google Drive/USB folder so backups survive losing the laptop.
BACKUP_COPY_DIR = os.environ.get("STUDIO_BACKUP_COPY_DIR") or None
BACKUP_KEEP = 60
# The Wix import preview posts two fields per person.
DATA_UPLOAD_MAX_NUMBER_FIELDS = 12_000

# Supplier prices are stored including VAT unless STUDIO_PRICES_EX_VAT=1 (e.g. if VAT-registered).
SUPPLIER_PRICES_INCLUDE_VAT = os.environ.get("STUDIO_PRICES_EX_VAT") != "1"

# Used in balance emails and printed statements.
STUDIO_NAME = "The Silver Bird"
STUDIO_SIGNOFF = os.environ.get("STUDIO_SIGNOFF", "Liz")

# Materials making less than this share of their student price as profit are flagged.
THIN_MARGIN_PERCENT = 15
