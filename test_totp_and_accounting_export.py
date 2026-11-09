"""Unit tests for Two-Factor Authentication (TOTP) and Accounting Export (Tally Prime & QuickBooks)."""

import io
import os
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from database.db import (
    get_connection, init_db, create_user, authenticate_user,
    enable_user_totp, disable_user_totp, get_user_by_id
)
from services.totp import (
    generate_totp_secret, get_totp_code, verify_totp,
    get_provisioning_uri, generate_qr_data_uri
)
from services.accounting_export import generate_tally_xml, generate_quickbooks_csv
from app import app


class TotpAndAccountingExportTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db_path = Path(self.temp_dir.name) / 'test_totp_export.db'
        init_db(self.db_path)

        with get_connection(self.db_path) as conn:
            conn.execute("""INSERT INTO documents
                (filename, document_type, upload_date, processing_status, file_hash, currency)
                VALUES ('bank_stmt.pdf', 'bank_statement', '2026-05-15', 'processed', 'hash-totp-1', 'INR')""")
            doc_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]

            conn.execute("""INSERT INTO transactions
                (document_id, transaction_date, description, debit, credit, category, currency)
                VALUES (?, '2026-05-10', 'Office Rent Payment', 25000.0, NULL, 'Rent & Facilities', 'INR')""",
                (doc_id,))
            conn.execute("""INSERT INTO transactions
                (document_id, transaction_date, description, debit, credit, category, currency)
                VALUES (?, '2026-05-12', 'Client Wire Transfer', NULL, 75000.0, 'Client Revenue', 'INR')""",
                (doc_id,))

            conn.execute("""INSERT INTO documents
                (filename, document_type, upload_date, processing_status, file_hash, currency)
                VALUES ('inv_office.pdf', 'invoice', '2026-05-14', 'processed', 'hash-totp-2', 'INR')""")
            inv_doc_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]

            conn.execute("""INSERT INTO invoices
                (document_id, invoice_number, invoice_date, vendor_name, total_amount, reconciliation_status, currency)
                VALUES (?, 'INV-2026-999', '2026-05-14', 'City Supplies Corp', 12500.0, 'PENDING', 'INR')""",
                (inv_doc_id,))

        app.config['TESTING'] = True
        self.client = app.test_client()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_totp_generation_and_verification(self):
        """Standard TOTP secret generation, code derivation, and RFC-6238 window verification."""
        secret = generate_totp_secret()
        self.assertTrue(len(secret) >= 16)

        current_code = get_totp_code(secret)
        self.assertEqual(len(current_code), 6)
        self.assertTrue(current_code.isdigit())

        # Correct code verifies
        self.assertTrue(verify_totp(secret, current_code))
        # Wrong code fails
        wrong_code = '000000' if current_code != '000000' else '111111'
        self.assertFalse(verify_totp(secret, wrong_code))
        # Invalid length or non-digits fail
        self.assertFalse(verify_totp(secret, '123'))
        self.assertFalse(verify_totp(secret, 'abcdef'))

        # Provisioning URI and QR data URI
        uri = get_provisioning_uri(secret, 'user@example.com', 'Atlas Finance')
        self.assertIn('otpauth://totp/', uri)
        self.assertIn(secret, uri)

        qr_data = generate_qr_data_uri(uri)
        self.assertTrue(qr_data.startswith('data:image/png;base64,'))

    def test_user_totp_database_lifecycle(self):
        """User account can enable and disable 2FA state cleanly."""
        user = create_user('totp_tester@atlas.com', 'SecureSecretPass123', 'TOTP Tester', db_path=self.db_path)
        self.assertFalse(user.get('totp_enabled', False))

        # Enable TOTP
        test_secret = generate_totp_secret()
        enable_user_totp(user['id'], test_secret, db_path=self.db_path)

        updated = get_user_by_id(user['id'], db_path=self.db_path)
        self.assertTrue(bool(updated['totp_enabled']))
        self.assertEqual(updated['totp_secret'], test_secret)

        # Authenticate returns 2FA status
        auth = authenticate_user('totp_tester@atlas.com', 'SecureSecretPass123', db_path=self.db_path)
        self.assertTrue(auth['totp_enabled'])

        # Disable TOTP
        disable_user_totp(user['id'], db_path=self.db_path)
        updated_disabled = get_user_by_id(user['id'], db_path=self.db_path)
        self.assertFalse(bool(updated_disabled['totp_enabled']))
        self.assertIsNone(updated_disabled['totp_secret'])

    def test_tally_xml_format_and_structure(self):
        """Tally Prime XML exporter produces valid, well-formed XML with standard vouchers."""
        xml_buf = generate_tally_xml(self.db_path)
        xml_content = xml_buf.getvalue()
        self.assertTrue(len(xml_content) > 500)

        # Parse XML tree to guarantee well-formed syntax
        root = ET.fromstring(xml_content)
        self.assertEqual(root.tag, 'ENVELOPE')
        header = root.find('HEADER')
        self.assertIsNotNone(header)
        self.assertEqual(header.find('TALLYREQUEST').text, 'Import Data')

        vouchers = root.findall('.//VOUCHER')
        # 2 transactions (Payment, Receipt) + 1 invoice (Purchase) = 3 vouchers
        self.assertEqual(len(vouchers), 3)

        vch_types = [v.get('VCHTYPE') for v in vouchers]
        self.assertIn('Payment', vch_types)
        self.assertIn('Receipt', vch_types)
        self.assertIn('Purchase', vch_types)

    def test_quickbooks_csv_generation(self):
        """QuickBooks CSV exporter produces standard Batch Enter format headers and rows."""
        csv_buf = generate_quickbooks_csv(self.db_path)
        csv_text = csv_buf.getvalue().decode('utf-8')
        lines = [line.strip() for line in csv_text.splitlines() if line.strip()]

        # Header check
        self.assertEqual(lines[0], 'Date,Transaction Type,Number,Name,Memo,Account,Debit,Credit')
        self.assertTrue(any('Check' in line for line in lines))
        self.assertTrue(any('Deposit' in line for line in lines))
        self.assertTrue(any('Bill' in line for line in lines))

    def test_export_endpoints_tally_and_quickbooks(self):
        """Flask export endpoints return proper attachments for tally and quickbooks."""
        res_tally = self.client.get('/analytics/export?format=tally')
        self.assertEqual(res_tally.status_code, 200)
        self.assertIn('application/xml', res_tally.headers.get('Content-Type'))
        self.assertIn(b'<ENVELOPE>', res_tally.data)

        res_qb = self.client.get('/analytics/export?format=quickbooks')
        self.assertEqual(res_qb.status_code, 200)
        self.assertIn('text/csv', res_qb.headers.get('Content-Type'))
        self.assertIn(b'Transaction Type', res_qb.data)

    def test_2fa_login_and_settings_flow(self):
        """2FA login prompt and settings view render and verify properly."""
        # Unauthenticated access to /login/2fa redirects to /login
        res = self.client.get('/login/2fa')
        self.assertEqual(res.status_code, 302)
        self.assertIn('/login', res.location)

        # Authenticated user can view security settings
        with self.client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['user_email'] = 'admin@atlasfinance.com'
            sess['user_name'] = 'Admin User'
            sess['user_role'] = 'admin'

        res_sec = self.client.get('/settings/security')
        self.assertEqual(res_sec.status_code, 200)
        self.assertIn(b'Two-Factor Authentication', res_sec.data)


if __name__ == '__main__':
    unittest.main()
