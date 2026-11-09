"""Focused Phase 4/5 analytics tests using an isolated SQLite database."""

import tempfile
import unittest
from pathlib import Path

from database.db import get_connection, init_db
from database.db import delete_document
from services.analytics import (
    get_financial_overview,
    get_reconciled_invoices,
    reconcile_invoices_and_transactions,
    detect_missing_periods,
)


class AnalyticsTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db_path = Path(self.temp_dir.name) / 'analytics.db'
        init_db(self.db_path)
        with get_connection(self.db_path) as conn:
            conn.execute("""INSERT INTO documents
                (filename, document_type, upload_date, processing_status, file_hash, currency)
                VALUES ('statement.pdf', 'bank_statement', '2026-04-30', 'processed', 'hash-statement', 'INR')""")
            statement_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
            conn.executemany("""INSERT INTO transactions
                (document_id, transaction_date, description, debit, credit, category, currency)
                VALUES (?, ?, ?, ?, ?, ?, ?)""", [
                    (statement_id, '2026-04-01', 'Salary', None, 50000, 'Income', 'INR'),
                    (statement_id, '2026-04-03', 'Rent', 25000, None, 'Housing', 'INR'),
                    (statement_id, '2026-05-02', 'Consulting', None, 30000, 'Income', 'INR'),
                ])
            conn.execute("""INSERT INTO documents
                (filename, document_type, upload_date, processing_status, file_hash, currency)
                VALUES ('invoice.pdf', 'invoice', '2026-04-10', 'processed', 'hash-invoice', 'INR')""")
            invoice_doc_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
            conn.execute("""INSERT INTO invoices
                (document_id, invoice_number, invoice_date, vendor_name, currency,
                 subtotal, tax, discount, total_amount)
                VALUES (?, 'INV-1', '2026-04-04', 'Acme Supplies', 'INR', 10000, 1800, 200, 11600)""", (invoice_doc_id,))

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_metrics_and_monthly_values_use_stored_data(self):
        overview = get_financial_overview(self.db_path)
        self.assertEqual(overview['total_income'], 80000.0)
        self.assertEqual(overview['total_expenses'], 25000.0)
        self.assertEqual(overview['net_cash_flow'], 55000.0)
        self.assertEqual(overview['transaction_count'], 3)
        self.assertEqual(overview['invoice_count'], 1)
        self.assertEqual(overview['total_invoiced'], 11600.0)
        self.assertEqual(overview['monthly_trends'][0]['month'], '2026-04')
        self.assertEqual(overview['monthly_trends'][0]['net'], 25000.0)
        self.assertEqual(overview['highest_expense'], 25000.0)
        self.assertEqual(len(overview['bank_statements']), 1)
        self.assertEqual(overview['bank_statements'][0]['transaction_count'], 3)

    def test_reconciliation_and_filters(self):
        reconcile_invoices_and_transactions(self.db_path)
        overview = get_financial_overview(self.db_path, {'month': '2026-04'})
        self.assertEqual(overview['transaction_count'], 2)
        self.assertEqual(overview['invoice_count'], 1)
        self.assertEqual(overview['paid_invoices'], 0)
        self.assertEqual(len(get_reconciled_invoices(self.db_path, {'document_type': 'invoice'})), 1)
        self.assertEqual(len(get_reconciled_invoices(self.db_path, {'document_type': 'bank_statement'})), 0)

    def test_empty_database_has_no_data_flag(self):
        empty_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        empty_path = Path(empty_dir.name) / 'empty.db'
        init_db(empty_path)
        self.assertFalse(get_financial_overview(empty_path)['has_data'])
        empty_dir.cleanup()

    def test_delete_document_cascades_child_records(self):
        with get_connection(self.db_path) as conn:
            document_id = conn.execute(
                "SELECT id FROM documents WHERE filename = 'statement.pdf'"
            ).fetchone()['id']
            conn.execute(
                "UPDATE documents SET stored_filename = 'stored-statement.pdf' WHERE id = ?",
                (document_id,),
            )

        self.assertEqual(delete_document(document_id, self.db_path), 'stored-statement.pdf')
        with get_connection(self.db_path) as conn:
            self.assertIsNone(conn.execute(
                "SELECT id FROM documents WHERE id = ?", (document_id,)
            ).fetchone())
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) AS count FROM transactions WHERE document_id = ?",
                (document_id,),
            ).fetchone()['count'], 0)

    def test_missing_periods_detection(self):
        # 1. Filter duration where intermediate month is missing
        # Insert a transaction in Jan 2026. April and May already exist from setUp.
        # So when filtering Jan 2026 to May 2026, Feb 2026 and March 2026 are missing in the middle!
        with get_connection(self.db_path) as conn:
            doc_id = conn.execute("SELECT id FROM documents WHERE filename = 'statement.pdf'").fetchone()['id']
            conn.execute("""INSERT INTO transactions
                (document_id, transaction_date, description, debit, credit, category, currency)
                VALUES (?, '2026-01-15', 'Opening Deposit', NULL, 10000, 'Income', 'INR')""", (doc_id,))

        overview = get_financial_overview(self.db_path, {
            'date_from': '2026-01-01',
            'date_to': '2026-04-30'
        })
        alert = overview['missing_data_alert']
        self.assertTrue(alert['has_missing'])
        self.assertTrue(alert['is_middle_gap'])
        self.assertEqual(alert['missing_months'], ['2026-02', '2026-03'])
        self.assertEqual(alert['missing_months_labels'], ['February 2026', 'March 2026'])
        self.assertIn('February 2026 and March 2026', alert['message'])
        self.assertEqual(alert['start_period'], 'January 2026')
        self.assertEqual(alert['end_period'], 'April 2026')

        # 2. Complete date duration with no gaps
        overview_complete = get_financial_overview(self.db_path, {
            'date_from': '2026-04-01',
            'date_to': '2026-05-31'
        })
        self.assertFalse(overview_complete['missing_data_alert']['has_missing'])

        # 3. Single month filter does not flag missing periods
        overview_single = get_financial_overview(self.db_path, {'month': '2026-04'})
        self.assertFalse(overview_single['missing_data_alert']['has_missing'])


if __name__ == '__main__':
    unittest.main()
