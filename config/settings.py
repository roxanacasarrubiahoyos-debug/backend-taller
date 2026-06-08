from pathlib import Path
import os
from dotenv import load_dotenv
from datetime import timedelta

load_dotenv(override=False)

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-!u)0rli+wnkf)$#)hs%a78enh$$j^_y*_$t3jy))1lxq-=^7q0')
DEBUG = os.getenv('DEBUG', 'True') == 'True'
ALLOWED_HOSTS = ['*']
# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Third-party
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'corsheaders',
    'django_filters',
    'drf_spectacular',
    'django_eventstream',
    'django_q',
    'channels',

    # Custom apps
    'apps.realtime.apps.RealtimeConfig',
    'apps.users.apps.UsersConfig',
    'apps.workshops.apps.WorkshopsConfig',
    'apps.vehicles.apps.VehiclesConfig',
    'apps.incidents.apps.IncidentsConfig',
    'apps.assignments.apps.AssignmentsConfig',
    'apps.payments.apps.PaymentsConfig',
    'apps.notifications.apps.NotificationsConfig',
    'apps.ai_engine.apps.AiEngineConfig',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'

CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels.layers.InMemoryChannelLayer',
    },
}

# Database
import dj_database_url

DATABASE_URL = os.getenv('DATABASE_URL')
if DATABASE_URL:
    DATABASES = {
        'default': dj_database_url.parse(DATABASE_URL, conn_max_age=600)
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.getenv('DB_NAME', 'emergencias_vehiculares'),
            'USER': os.getenv('DB_USER', 'postgres'),
            'PASSWORD': os.getenv('DB_PASSWORD', 'postgres'),
            'HOST': os.getenv('DB_HOST', 'localhost'),
            'PORT': os.getenv('DB_PORT', '5432'),
        }
    }

# Custom User Model
AUTH_USER_MODEL = 'users.User'

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
LANGUAGE_CODE = 'es'
TIME_ZONE = 'America/La_Paz'
USE_I18N = True
USE_TZ = True

# Static files
STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# Media files (uploaded content - LOCAL storage)
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Upload limits
DATA_UPLOAD_MAX_MEMORY_SIZE = 52428800   # 50 MB
FILE_UPLOAD_MAX_MEMORY_SIZE = 52428800

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# REST Framework
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
}

# JWT Settings
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=2),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=30),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'ALGORITHM': 'HS256',
    'AUTH_HEADER_TYPES': ('Bearer',),
}

# Django Q2 (async tasks - uses ORM, no Redis)
Q_CLUSTER = {
    'name': 'emergencias',
    'workers': 4,
    'timeout': 120,
    'retry': 200,
    'queue_limit': 50,
    'orm': 'default',  # Uses PostgreSQL as broker
}

# CORS Settings
# Orígenes típicos de `ng serve` (añadí host LAN frecuente; sobreescribir con env si hace falta).
_default_cors = 'http://localhost:4200,http://127.0.0.1:4200,http://192.168.100.200:4200,http://192.168.100.200:8081'
CORS_ALLOWED_ORIGINS = [
    o.strip() for o in os.getenv('CORS_ALLOWED_ORIGINS', _default_cors).split(',') if o.strip()
]
CORS_ALLOWED_ORIGIN_REGEXES = [
    r"^https://.*\.vercel\.app$",
]
CORS_ALLOW_CREDENTIALS = True

# DRF Spectacular (API docs)
SPECTACULAR_SETTINGS = {
    'TITLE': 'Emergencias Vehiculares API',
    'DESCRIPTION': 'Plataforma Inteligente de Atención de Emergencias Vehiculares',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'COMPONENT_SPLIT_REQUEST': True,
}

# External Services Configuration

# Stripe
STRIPE_SECRET_KEY = os.getenv('STRIPE_SECRET_KEY', '')
STRIPE_PUBLISHABLE_KEY = os.getenv('STRIPE_PUBLISHABLE_KEY', '')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET', '')

# OpenAI
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')

# Firebase (push notifications — app móvil cliente/técnico)
FIREBASE_CREDENTIALS_PATH = os.getenv('FIREBASE_CREDENTIALS_PATH', '')

# Web Push VAPID (panel Angular taller/admin — sin Firebase)
WEB_PUSH_VAPID_PUBLIC_KEY = os.getenv('WEB_PUSH_VAPID_PUBLIC_KEY', '')
WEB_PUSH_VAPID_PRIVATE_KEY = os.getenv('WEB_PUSH_VAPID_PRIVATE_KEY', '')
WEB_PUSH_VAPID_CLAIMS_EMAIL = os.getenv(
    'WEB_PUSH_VAPID_CLAIMS_EMAIL',
    'mailto:admin@appemergencias.local',
)
# Panel web: encolar BD + SSE + Web Push con django-q (`python manage.py qcluster`)
WEB_PANEL_NOTIFY_ASYNC = os.getenv('WEB_PANEL_NOTIFY_ASYNC', 'True').lower() == 'true'
# URL del panel Angular (Stripe Checkout success/cancel)
FRONTEND_URL = os.getenv('FRONTEND_URL', 'http://localhost:4200')
# Opcional: token de Expo (expo.dev) para mayor límite de rate en push API
EXPO_ACCESS_TOKEN = os.getenv('EXPO_ACCESS_TOKEN', '')

# TensorFlow Model Paths
TF_MODEL_PATH = BASE_DIR / 'ml_models' / 'incident_classifier' / 'model.h5'
TF_LABELS_PATH = BASE_DIR / 'ml_models' / 'incident_classifier' / 'labels.json'

# Motor de asignación: si True, también se ofrece a talleres activos aún no verificados por admin (útil en desarrollo).
ASSIGNMENT_ALLOW_UNVERIFIED = os.getenv(
    'ASSIGNMENT_ALLOW_UNVERIFIED',
    'True' if DEBUG else 'False',
).lower() == 'true'

# Si False, talleres sin suscripción activa no reciben ofertas (en DEBUG por defecto no se exige).
ASSIGNMENT_REQUIRE_SUBSCRIPTION = os.getenv(
    'ASSIGNMENT_REQUIRE_SUBSCRIPTION',
    'False' if DEBUG else 'True',
).lower() == 'true'

# Django Eventstream (SSE)
EVENTSTREAM_ALLOW_ORIGINS = CORS_ALLOWED_ORIGINS
EVENTSTREAM_CHANNELMANAGER_CLASS = 'apps.notifications.channel_manager.PanelWebChannelManager'

CSRF_TRUSTED_ORIGINS = [
    o.strip() for o in os.getenv('CSRF_TRUSTED_ORIGINS', '').split(',') if o.strip()
]