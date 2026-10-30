import os
import unittest
from pathlib import Path
from starlette.testclient import TestClient

from cryptography.fernet import Fernet
import tempfile

ROOT = Path(__file__).resolve().parents[1]
temp_db = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
temp_db_path = temp_db.name
temp_db.close()

os.environ['JWT_SECRET'] = 'test-secret-at-least-32-chars-long-for-testing'
os.environ['API_KEY_ENCRYPTION_KEY'] = Fernet.generate_key().decode()
os.environ['DATABASE_URL'] = f'sqlite:///{temp_db_path}'
os.environ['KUMUTA_ENV'] = 'development'

dist_dir = Path(__file__).resolve().parents[2] / 'frontend' / 'dist'
if not (dist_dir / 'index.html').exists():
    _mock_dist = tempfile.TemporaryDirectory()
    dist_dir = Path(_mock_dist.name)
    (dist_dir / 'index.html').write_text('<!DOCTYPE html><html><body><div id="root"></div></body></html>')
    (dist_dir / 'canvas.html').write_text('<!DOCTYPE html><html><head><title>Kumuta Canvas</title></head><body>Kumuta Canvas</body></html>')
    (dist_dir / 'kumuta.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg"></svg>')
os.environ['FRONTEND_DIST'] = str(dist_dir)

from app.server import app

class ServerTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_health(self):
        res = self.client.get('/health')
        self.assertEqual(res.status_code, 200)
        self.assertIn('status', res.json())
        self.assertEqual(res.json()['status'], 'ok')

    def test_api_health(self):
        res = self.client.get('/api/health')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()['status'], 'ok')

    def test_chatbot_spa_root(self):
        res = self.client.get('/')
        self.assertEqual(res.status_code, 200)
        self.assertIn('text/html', res.headers.get('content-type', ''))
        self.assertIn('<div id="root">', res.text)
        self.assertEqual(res.headers.get('x-content-type-options'), 'nosniff')

    def test_canvas_spa_route(self):
        for path in ('/canvas', '/canvas/', '/canvas.html'):
            res = self.client.get(path)
            self.assertEqual(res.status_code, 200, f'Path {path} failed')
            self.assertIn('text/html', res.headers.get('content-type', ''))
            self.assertIn('Kumuta Canvas', res.text)
            self.assertEqual(res.headers.get('x-content-type-options'), 'nosniff')

    def test_spa_nested_route_fallback(self):
        res = self.client.get('/workspace/123')
        self.assertEqual(res.status_code, 200)
        self.assertIn('<div id="root">', res.text)

        res_canvas = self.client.get('/canvas/library')
        self.assertEqual(res_canvas.status_code, 200)
        self.assertIn('Kumuta Canvas', res_canvas.text)

    def test_missing_asset_returns_404(self):
        res = self.client.get('/assets/nonexistent.js')
        self.assertEqual(res.status_code, 404)

    def test_static_asset_serving(self):
        res = self.client.get('/kumuta.svg')
        self.assertEqual(res.status_code, 200)
        self.assertIn('svg', res.headers.get('content-type', ''))

    def test_api_routing_and_auth(self):
        # /api/models requires auth; should return 401
        res = self.client.get('/api/models')
        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.json()['detail'], 'Sign in to continue')

        # Test signup via /api/auth/signup
        res_signup = self.client.post('/api/auth/signup', json={'email': 'demo@example.com', 'password': 'password123'})
        self.assertEqual(res_signup.status_code, 200)
        token = res_signup.json()['token']
        self.assertTrue(token)

        # /api/models requires user Gemini API key; should return 428 Precondition Required
        res_models = self.client.get('/api/models', headers={'Authorization': f'Bearer {token}'})
        self.assertEqual(res_models.status_code, 428)
        self.assertIn('Add your Gemini API key', res_models.json()['detail'])

        # Check /api/auth/me returns 200 with user data
        res_me = self.client.get('/api/auth/me', headers={'Authorization': f'Bearer {token}'})
        self.assertEqual(res_me.status_code, 200)
        self.assertEqual(res_me.json()['email'], 'demo@example.com')

if __name__ == '__main__':
    unittest.main()
