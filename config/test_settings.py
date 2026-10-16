import os
import atexit
import shutil
import tempfile
os.environ.setdefault('DJANGO_SECRET_KEY','test-only-key-not-for-production-01234567890123456789')
os.environ.setdefault('DATABASE_URL','sqlite://:memory:')
from .settings import *
DATABASES = {'default': env.db('TEST_DATABASE_URL', default='sqlite://:memory:')}
GEMINI_API_KEY = 'test-only-no-real-provider-access'
TEST_RUNNER = 'tests.runner.OfflineAITestRunner'
MEDIA_ROOT = tempfile.mkdtemp(prefix='cv-maker-test-media-')
atexit.register(shutil.rmtree, MEDIA_ROOT, ignore_errors=True)
SECURE_SSL_REDIRECT = False
REST_FRAMEWORK = {**REST_FRAMEWORK, 'DEFAULT_THROTTLE_CLASSES':[]}
