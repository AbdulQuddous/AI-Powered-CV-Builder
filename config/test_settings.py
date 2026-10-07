import os
os.environ.setdefault('DJANGO_SECRET_KEY','test-only-key-not-for-production-01234567890123456789')
os.environ.setdefault('DATABASE_URL','sqlite://:memory:')
from .settings import *
SECURE_SSL_REDIRECT = False
REST_FRAMEWORK = {**REST_FRAMEWORK, 'DEFAULT_THROTTLE_CLASSES':[]}
