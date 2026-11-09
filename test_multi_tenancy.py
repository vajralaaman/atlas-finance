"""Tests for Multi-Tenant User Account Data Isolation in Atlas Finance."""

import tempfile
import unittest
import sqlite3
from pathlib import Path

from app import app
from config import DATABASE_PATH
from database.db import (
    init_db,
    create_user,
    save_document,
    search_documents,
    get_document_bundle,
    delete_document,
    get_connection,
)
from services.analytics import (
    get_financial_overview,
    reconcile_invoices_and_transactions,
)


class MultiTenancyTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db_path = Path(self.temp_dir.name) / 'tenants.db'
        init_db(self.db_path)

        # Create two distinct users
        self.user_a = create_user('usera@finance.com', 'password123', 'User Alpha', db_path=self.db_path)
        self.user_b = create_user('userb@finance.com', 'password456', 'User Beta', db_path=self.db_path)
        self.assertNotEqual(self.user_a['id'], self.user_b['id'])

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_document_isolation_between_accounts(self):
        """User B cannot see documents uploaded by User A."""
        meta_a = {
            'filename': 'alpha_statement.pdf',
            'document_type': 'bank_statement',
            'upload_date': '2026-04-15 10:00:00',
            'page_count': 1,
            'processing_status': 'processed',
            'extracted_text': 'Alpha Corp Statement',
        }
        data_a = {
            'statement_information': {'currency': 'INR', 'bank_name': 'HDFC'},
            'transactions': [
                {'date': '2026-04-01', 'description': 'Client Payment', 'debit': None, 'credit': 75000, 'category': 'Income'},
                {'date': '2026-04-05', 'description': 'Office Supplies', 'debit': 15000, 'credit': None, 'category': 'Office'},
            ],
        }
        bundle_a, is_dup = save_document(meta_a, data_a, 'hash-doc-alpha', self.db_path, user_id=self.user_a['id'])
        self.assertFalse(is_dup)

        # User A searches documents -> sees 1 document
        docs_a = search_documents('', db_path=self.db_path, user_id=self.user_a['id'])
        self.assertEqual(len(docs_a), 1)
        self.assertEqual(docs_a[0]['filename'], 'alpha_statement.pdf')

        # User B searches documents -> sees 0 documents
        docs_b = search_documents('', db_path=self.db_path, user_id=self.user_b['id'])
        self.assertEqual(len(docs_b), 0)

    def test_anti_idor_authorization_protection(self):
        """User B cannot inspect or delete User A's document."""
        meta_a = {
            'filename': 'confidential_payroll.pdf',
            'document_type': 'bank_statement',
            'upload_date': '2026-04-15 10:00:00',
            'page_count': 1,
            'processing_status': 'processed',
        }
        bundle_a, _ = save_document(meta_a, None, 'hash-confidential', self.db_path, user_id=self.user_a['id'])
        doc_a_id = bundle_a['document']['id']

        # User B attempts to access User A's document bundle
        bundle_attempt = get_document_bundle(doc_a_id, db_path=self.db_path, user_id=self.user_b['id'])
        self.assertIsNone(bundle_attempt, "User B should be blocked from accessing User A's document")

        # User B attempts to delete User A's document
        delete_attempt = delete_document(doc_a_id, db_path=self.db_path, user_id=self.user_b['id'])
        self.assertIsNone(delete_attempt, "User B should be blocked from deleting User A's document")

        # Document still exists for User A
        bundle_still_exists = get_document_bundle(doc_a_id, db_path=self.db_path, user_id=self.user_a['id'])
        self.assertIsNotNone(bundle_still_exists)

    def test_scoped_deduplication_allows_distinct_user_uploads(self):
        """Two separate users can upload the exact same file without cross-user collision."""
        identical_hash = 'sha256-identical-sample-file'
        meta = {
            'filename': 'invoice_march.pdf',
            'document_type': 'invoice',
            'upload_date': '2026-03-01 10:00:00',
            'page_count': 1,
            'processing_status': 'processed',
        }

        # User A uploads
        _, is_dup_a = save_document(meta, None, identical_hash, self.db_path, user_id=self.user_a['id'])
        self.assertFalse(is_dup_a)

        # User B uploads the same file -> NOT duplicate for User B
        _, is_dup_b = save_document(meta, None, identical_hash, self.db_path, user_id=self.user_b['id'])
        self.assertFalse(is_dup_b, "User B upload should NOT collide with User A's file hash")

        # User A uploads the same file again -> IS duplicate for User A
        _, is_dup_a2 = save_document(meta, None, identical_hash, self.db_path, user_id=self.user_a['id'])
        self.assertTrue(is_dup_a2, "Re-upload by same user should be flagged as duplicate")

    def test_legacy_global_hash_constraint_is_migrated(self):
        """A legacy global hash constraint must not block another user's upload."""
        legacy_path = Path(self.temp_dir.name) / 'legacy.db'
        with sqlite3.connect(legacy_path) as conn:
            conn.executescript("""
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    full_name TEXT,
                    role TEXT NOT NULL DEFAULT 'admin'
                );
                INSERT INTO users (email, password_hash, full_name) VALUES
                    ('first@example.com', 'hash', 'First'),
                    ('second@example.com', 'hash', 'Second');
                CREATE TABLE documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    filename TEXT NOT NULL,
                    document_type TEXT NOT NULL,
                    upload_date TEXT NOT NULL,
                    page_count INTEGER NOT NULL DEFAULT 0,
                    processing_status TEXT NOT NULL,
                    extracted_text TEXT NOT NULL DEFAULT '',
                    file_hash TEXT NOT NULL UNIQUE,
                    stored_filename TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    user_id INTEGER
                );
                INSERT INTO documents
                    (filename, document_type, upload_date, processing_status, file_hash, user_id)
                VALUES ('existing.pdf', 'invoice', '2026-10-01', 'processed', 'same-hash', 1);
            """)

        init_db(legacy_path)
        with get_connection(legacy_path) as conn:
            save_document(
                {'filename': 'same.pdf', 'document_type': 'invoice',
                 'upload_date': '2026-10-02', 'processing_status': 'processed'},
                None, 'same-hash', legacy_path, user_id=2
            )
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) FROM documents WHERE file_hash = 'same-hash'"
            ).fetchone()[0], 2)

    def test_analytics_metrics_strict_isolation(self):
        """Financial metrics and totals only aggregate the authenticated user's records."""
        # User A data: Income 100,000, Expense 40,000
        meta_a = {'filename': 'stmt_a.pdf', 'document_type': 'bank_statement', 'upload_date': '2026-04-10', 'processing_status': 'processed'}
        data_a = {
            'statement_information': {'currency': 'INR'},
            'transactions': [
                {'date': '2026-04-01', 'description': 'A Income', 'debit': None, 'credit': 100000},
                {'date': '2026-04-05', 'description': 'A Expense', 'debit': 40000, 'credit': None},
            ],
        }
        save_document(meta_a, data_a, 'hash-a-metrics', self.db_path, user_id=self.user_a['id'])

        # User B data: Income 25,000, Expense 5,000
        meta_b = {'filename': 'stmt_b.pdf', 'document_type': 'bank_statement', 'upload_date': '2026-04-12', 'processing_status': 'processed'}
        data_b = {
            'statement_information': {'currency': 'INR'},
            'transactions': [
                {'date': '2026-04-02', 'description': 'B Income', 'debit': None, 'credit': 25000},
                {'date': '2026-04-06', 'description': 'B Expense', 'debit': 5000, 'credit': None},
            ],
        }
        save_document(meta_b, data_b, 'hash-b-metrics', self.db_path, user_id=self.user_b['id'])

        overview_a = get_financial_overview(self.db_path, user_id=self.user_a['id'])
        self.assertEqual(overview_a['total_income'], 100000.0)
        self.assertEqual(overview_a['total_expenses'], 40000.0)
        self.assertEqual(overview_a['net_cash_flow'], 60000.0)

        overview_b = get_financial_overview(self.db_path, user_id=self.user_b['id'])
        self.assertEqual(overview_b['total_income'], 25000.0)
        self.assertEqual(overview_b['total_expenses'], 5000.0)
        self.assertEqual(overview_b['net_cash_flow'], 20000.0)

    def test_reconciliation_cross_contamination_prevented(self):
        """User B's payments cannot reconcile User A's invoices."""
        # User A uploads an invoice for 12,000 to 'Supplier X'
        meta_inv_a = {'filename': 'inv_a.pdf', 'document_type': 'invoice', 'upload_date': '2026-04-01', 'processing_status': 'processed'}
        data_inv_a = {
            'invoice_number': 'INV-A-101',
            'vendor_name': 'Supplier X',
            'invoice_date': '2026-04-01',
            'total_amount': 12000.0,
        }
        save_document(meta_inv_a, data_inv_a, 'hash-inv-a', self.db_path, user_id=self.user_a['id'])

        # User B uploads a bank statement with a debit of 12,000 to 'Supplier X'
        meta_stmt_b = {'filename': 'stmt_b.pdf', 'document_type': 'bank_statement', 'upload_date': '2026-04-05', 'processing_status': 'processed'}
        data_stmt_b = {
            'statement_information': {'currency': 'INR'},
            'transactions': [
                {'date': '2026-04-05', 'description': 'Supplier X Payment', 'debit': 12000.0, 'credit': None},
            ],
        }
        save_document(meta_stmt_b, data_stmt_b, 'hash-stmt-b', self.db_path, user_id=self.user_b['id'])

        # Reconcile User A -> Invoice A should remain PENDING because User A has no debits
        reconcile_invoices_and_transactions(self.db_path, user_id=self.user_a['id'])
        with get_connection(self.db_path) as conn:
            inv_a = conn.execute("SELECT reconciliation_status FROM invoices WHERE invoice_number = 'INV-A-101'").fetchone()
            self.assertEqual(inv_a['reconciliation_status'], 'PENDING')

        # Now User A uploads their own debit of 12,000
        meta_stmt_a = {'filename': 'stmt_a.pdf', 'document_type': 'bank_statement', 'upload_date': '2026-04-06', 'processing_status': 'processed'}
        data_stmt_a = {
            'statement_information': {'currency': 'INR'},
            'transactions': [
                {'date': '2026-04-06', 'description': 'Supplier X Payment', 'debit': 12000.0, 'credit': None},
            ],
        }
        save_document(meta_stmt_a, data_stmt_a, 'hash-stmt-a', self.db_path, user_id=self.user_a['id'])

        # Reconcile User A -> Now it matches User A's debit
        reconcile_invoices_and_transactions(self.db_path, user_id=self.user_a['id'])
        with get_connection(self.db_path) as conn:
            inv_a_after = conn.execute("SELECT reconciliation_status FROM invoices WHERE invoice_number = 'INV-A-101'").fetchone()
            self.assertEqual(inv_a_after['reconciliation_status'], 'PAID')

    def test_web_route_idor_isolation(self):
        """Flask route /documents/<id> returns 404 when requested by a different user session."""
        meta_a = {'filename': 'private_a.pdf', 'document_type': 'bank_statement', 'upload_date': '2026-04-01', 'processing_status': 'processed'}
        bundle_a, _ = save_document(meta_a, None, 'hash-private-a', DATABASE_PATH, user_id=self.user_a['id'])
        doc_id = bundle_a['document']['id']

        client = app.test_client()

        # Log in as User B
        with client.session_transaction() as sess:
            sess['user_id'] = self.user_b['id']
            sess['user_email'] = 'userb@finance.com'
            sess['user_role'] = 'admin'

        # Attempt to access User A's document detail
        res = client.get(f'/documents/{doc_id}')
        self.assertEqual(res.status_code, 404)

        # Log in as User A
        with client.session_transaction() as sess:
            sess['user_id'] = self.user_a['id']
            sess['user_email'] = 'usera@finance.com'
            sess['user_role'] = 'admin'

        # Access User A's own document detail -> 200 OK
        res_a = client.get(f'/documents/{doc_id}')
        self.assertEqual(res_a.status_code, 200)

        # Cleanup created doc from DATABASE_PATH
        delete_document(doc_id, DATABASE_PATH, user_id=self.user_a['id'])


if __name__ == '__main__':
    unittest.main()
