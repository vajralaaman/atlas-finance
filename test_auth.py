"""Authentication and user session tests for Atlas Finance."""

import tempfile
import unittest
from pathlib import Path
from werkzeug.security import check_password_hash

import sys
sys.path.insert(0, str(Path(__file__).parent))

from database.db import init_db, create_user, authenticate_user, get_user_by_id, get_connection
from app import app


class AuthenticationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db_path = Path(self.temp_dir.name) / 'auth_test.db'
        init_db(self.db_path)

        app.config['TESTING'] = False  # Enable auth check testing
        self.client = app.test_client()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_default_demo_user_seeded(self):
        """Default administrator account is automatically initialized."""
        user = authenticate_user('admin@atlasfinance.com', 'admin123', self.db_path)
        self.assertIsNotNone(user)
        self.assertEqual(user['email'], 'admin@atlasfinance.com')
        self.assertEqual(user['full_name'], 'Admin User')

    def test_user_registration_and_password_hashing(self):
        """New user can register and password is encrypted in database."""
        new_user = create_user('finance@startup.com', 'SecurePass123', 'John Doe', self.db_path)
        self.assertIsNotNone(new_user['id'])
        self.assertEqual(new_user['email'], 'finance@startup.com')
        self.assertEqual(new_user['full_name'], 'John Doe')

        with get_connection(self.db_path) as conn:
            row = conn.execute("SELECT password_hash FROM users WHERE email = 'finance@startup.com'").fetchone()
            # Verify password is not stored plaintext
            self.assertNotEqual(row['password_hash'], 'SecurePass123')
            self.assertTrue(check_password_hash(row['password_hash'], 'SecurePass123'))

    def test_duplicate_email_registration_rejected(self):
        """Cannot register twice with the same email."""
        create_user('duplicate@company.com', 'password123', 'First User', self.db_path)
        with self.assertRaises(ValueError):
            create_user('duplicate@company.com', 'different456', 'Second User', self.db_path)

    def test_short_password_and_invalid_email_rejected(self):
        """Validates minimum password length and email structure."""
        with self.assertRaises(ValueError):
            create_user('invalid-email-format', 'validPass123', 'Test', self.db_path)
        with self.assertRaises(ValueError):
            create_user('valid@company.com', '123', 'Test', self.db_path)

    def test_authentication_success_and_failure(self):
        """Correct credentials succeed; bad password or email returns None."""
        create_user('analyst@company.com', 'Password999', 'Analyst', self.db_path)

        # Success
        user = authenticate_user('analyst@company.com', 'Password999', self.db_path)
        self.assertIsNotNone(user)

        # Case-insensitive email
        user_upper = authenticate_user('ANALYST@Company.COM', 'Password999', self.db_path)
        self.assertIsNotNone(user_upper)

        # Wrong password
        wrong_pass = authenticate_user('analyst@company.com', 'WrongPassword', self.db_path)
        self.assertIsNone(wrong_pass)

        # Unknown email
        unknown = authenticate_user('ghost@unknown.com', 'Password999', self.db_path)
        self.assertIsNone(unknown)

    def test_protected_routes_require_login(self):
        """Unauthenticated requests to dashboard or documents redirect to /login."""
        res_analytics = self.client.get('/analytics')
        self.assertEqual(res_analytics.status_code, 302)
        self.assertIn('/login', res_analytics.location)

        res_docs = self.client.get('/documents')
        self.assertEqual(res_docs.status_code, 302)
        self.assertIn('/login', res_docs.location)

    def test_login_flow_and_session_access(self):
        """User logs in via POST, accesses dashboard, and logs out."""
        # 1. Login with demo account
        login_res = self.client.post('/login', data={
            'email': 'admin@atlasfinance.com',
            'password': 'admin123'
        }, follow_redirects=True)

        self.assertEqual(login_res.status_code, 200)
        self.assertIn('Dashboard', login_res.get_data(as_text=True))

        # 2. Can now access protected views
        dash_res = self.client.get('/analytics')
        self.assertEqual(dash_res.status_code, 200)

        # 3. Logout clears session
        logout_res = self.client.get('/logout', follow_redirects=True)
        self.assertEqual(logout_res.status_code, 200)
        self.assertIn('Sign in to Atlas Finance', logout_res.get_data(as_text=True))

        # 4. Attempting dashboard after logout redirects back to login
        dash_after_logout = self.client.get('/analytics')
        self.assertEqual(dash_after_logout.status_code, 302)
        self.assertIn('/login', dash_after_logout.location)


if __name__ == '__main__':
    unittest.main()
