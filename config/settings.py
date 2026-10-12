"""Django settings for the fuel route optimizer."""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-insecure-key-change-me")
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,testserver").split(",")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "fuelroute",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

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
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

# Trip plans are cached, so repeated requests (and the /map view for a plan
# that was just computed) never hit the external routing API again.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "fuelroute",
        "TIMEOUT": 60 * 60 * 6,
    }
}

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Fuel route planner -----------------------------------------------------
FUELROUTE = {
    "MAX_RANGE_MILES": 500.0,
    "MILES_PER_GALLON": 10.0,
    # Stations are geocoded to their city centroid, so allow some slack when
    # deciding whether a station is "on" the route.
    "MAX_DETOUR_MILES": 10.0,
    # The vehicle leaves with an empty tank and fuels up before leaving town:
    # any station within this many route-miles of the start counts as mile 0.
    "ORIGIN_RADIUS_MILES": 30.0,
    # Planning cost of one extra stop, in dollars. Stops the plan from pulling over
    # for a gallon to save a few cents; it is NOT added to the reported fuel cost.
    # Set to 0 for the strictly cheapest plan.
    "STOP_PENALTY_USD": 10.0,
    "OSRM_URL": os.environ.get("OSRM_URL", "https://router.project-osrm.org"),
    "NOMINATIM_URL": os.environ.get("NOMINATIM_URL", "https://nominatim.openstreetmap.org"),
    "HTTP_TIMEOUT_SECONDS": 15,
    "USER_AGENT": "fuel-route-optimizer/1.0 (assessment project)",
}
