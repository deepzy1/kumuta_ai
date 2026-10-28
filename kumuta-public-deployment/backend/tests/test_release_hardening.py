"""D7-9 adversarial auth/deployment checks on disposable data, no provider I/O."""
import os
import time
import unittest
from unittest.mock import patch

import jwt
from starlette.requests import Request
from sqlalchemy import select
import test_api as fixture
from app import browser_sessions as browser, deployment, documents, main
from app.database import SessionLocal, User


class ReleaseSecurityTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixture.APITests.asyncSetUp
    asyncTearDown = fixture.APITests.asyncTearDown
    call = fixture.APITests.call

    async def test_expiry_identity_contract_on_request_exchange_and_stream(self):
        uid = (await self.call('GET', '/auth/me')).json()['id']
        for claims in ({'sub': str(uid)}, {'exp': time.time()+60},
                       {'sub': None, 'exp': time.time()+60},
                       {'sub': '-1', 'exp': time.time()+60},
                       {'sub': str(uid), 'exp': time.time()-1},
                       {'sub': str(uid), 'exp': 'invalid'}):
            token = jwt.encode(claims, main.SECRET, algorithm='HS256')
            headers = {'Authorization': 'Bearer '+token}
            self.assertEqual((await self.client.get('/auth/me', headers=headers)).status_code, 401)
            self.assertEqual((await self.client.post('/auth/browser-session', headers={
                **headers, 'Origin': 'http://test', browser.CSRF_HEADER: '1'})).status_code, 401)
            request = Request({'type': 'http', 'headers': [(b'authorization', ('Bearer '+token).encode())]})
            with SessionLocal() as db:
                self.assertFalse(browser.stream_valid(request, uid, db, main.SECRET))
        self.assertEqual((await self.call('GET', '/auth/me')).status_code, 200)
        self.assertEqual(fixture.FakeClient.calls, [])

    async def test_private_and_denied_responses_are_never_cached(self):
        for path, headers in [('/conversations', self.headers), ('/settings/ui', self.headers),
                              ('/documents/999999/download', self.headers),
                              ('/conversations/999999', {}), ('/auth/session', {})]:
            response = await self.client.get(path, headers=headers)
            self.assertIn('no-store', response.headers['cache-control'])
            self.assertEqual(response.headers['x-content-type-options'], 'nosniff')
            self.assertEqual(response.headers['referrer-policy'], 'no-referrer')
            self.assertEqual(response.headers['x-frame-options'], 'DENY')

    async def test_registration_denial_preserves_accounts_and_login(self):
        with SessionLocal() as db:
            before = len(list(db.scalars(select(User.id))))
        with patch.dict(os.environ, {'KUMUTA_ENV': 'production', 'KUMUTA_ALLOW_REGISTRATION': 'false'}):
            response = await self.client.post('/auth/signup', json={'email': 'denied@example.com', 'password': 'password123'})
            self.assertEqual(response.status_code, 403)
            self.assertEqual((await self.call('GET', '/auth/me')).status_code, 200)
        with SessionLocal() as db:
            self.assertEqual(len(list(db.scalars(select(User.id)))), before)

    async def test_production_cookie_secure_even_with_internal_http(self):
        with patch.dict(os.environ, {'KUMUTA_ENV': 'production'}):
            response = await self.client.post('/auth/browser-session', headers={**self.headers,
                'Origin': 'http://test', browser.CSRF_HEADER: '1'})
            self.assertEqual(response.status_code, 200)
            self.assertIn('Secure', response.headers['set-cookie'])
            self.assertIn('HttpOnly', response.headers['set-cookie'])

    async def test_readiness_handles_missing_storage_and_database_without_leaks(self):
        documents.ensure_storage()
        self.assertEqual((await self.client.get('/ready')).status_code, 200)
        with patch.object(documents, 'STORAGE', documents.STORAGE / 'unavailable'):
            response = await self.client.get('/ready')
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.json(), {'status': 'not_ready'})
            self.assertNotIn(str(documents.STORAGE), response.text)
        with patch('sqlite3.connect', side_effect=OSError('private path and secret')):
            response = await self.client.get('/ready')
            self.assertEqual(response.status_code, 503)
            self.assertNotIn('secret', response.text)


class ProductionConfigurationTests(unittest.TestCase):
    def settings(self):
        return {'KUMUTA_ENV': 'production', 'CORS_ORIGINS': 'https://kumuta.example.com',
                'DATABASE_URL': 'sqlite:////srv/kumuta/private/chat.db',
                'DOCUMENT_STORAGE_DIR': '/srv/kumuta/private/documents',
                'JWT_SECRET': 'a-generated-secret-for-testing-'*2,
                'KUMUTA_ALLOW_REGISTRATION': 'false'}

    def test_production_rejects_unsafe_environment(self):
        for field, value in [('CORS_ORIGINS', '*'), ('CORS_ORIGINS', 'http://example.com'),
                             ('CORS_ORIGINS', 'https://example.com/path'),
                             ('DATABASE_URL', 'sqlite:///chat.db'),
                             ('DOCUMENT_STORAGE_DIR', 'public/uploads'),
                             ('JWT_SECRET', 'replace_with_a_long_random_secret_at_least_32_characters'),
                             ('KUMUTA_ALLOW_REGISTRATION', 'true'), ('KUMUTA_ENV', 'prod')]:
            with self.subTest(field=field, value=value), patch.dict(os.environ, {**self.settings(), field: value}, clear=True):
                with self.assertRaises(RuntimeError):
                    deployment.validate()

    def test_valid_production_and_local_defaults(self):
        with patch.dict(os.environ, self.settings(), clear=True):
            deployment.validate()
            self.assertFalse(deployment.registration_enabled())
        with patch.dict(os.environ, {}, clear=True):
            deployment.validate()
            self.assertTrue(deployment.registration_enabled())
