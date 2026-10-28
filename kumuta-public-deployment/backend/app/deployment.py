"""Small, fail-closed production profile; development stays local by default."""
import os
from pathlib import Path
from urllib.parse import urlsplit


def production():
    return os.getenv('KUMUTA_ENV', 'development').lower() == 'production'


def registration_enabled():
    return os.getenv('KUMUTA_ALLOW_REGISTRATION', 'false' if production() else 'true').lower() == 'true'


def validate():
    mode = os.getenv('KUMUTA_ENV', 'development').lower()
    if mode not in ('development', 'test', 'production'):
        raise RuntimeError('KUMUTA_ENV must be development, test or production')
    if not production():
        return
    origins = os.getenv('CORS_ORIGINS', '').split(',')
    for origin in origins:
        parsed = urlsplit(origin.strip())
        if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
                or parsed.path or parsed.query or parsed.fragment or '*' in origin):
            raise RuntimeError('Production CORS_ORIGINS must contain explicit HTTPS origins without paths')
    database = os.getenv('DATABASE_URL', '')
    if not database.startswith('sqlite:////') or '?' in database or '#' in database:
        raise RuntimeError('Production DATABASE_URL must be an absolute SQLite file URL')
    storage = os.getenv('DOCUMENT_STORAGE_DIR', '')
    if not storage or not Path(storage).is_absolute():
        raise RuntimeError('Production DOCUMENT_STORAGE_DIR must be an absolute private path')
    secret = os.getenv('JWT_SECRET', '')
    if len(secret) < 32 or secret.startswith(('replace_', 'test-', 'test_')):
        raise RuntimeError('Production JWT_SECRET must be a generated secret')
    if os.getenv('KUMUTA_ALLOW_REGISTRATION', 'false').lower() != 'false':
        raise RuntimeError('Production registration remains disabled pending an approved enrollment policy')
