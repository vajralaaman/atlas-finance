"""Unit tests for Financial Report Exporting and Risk & Anomaly Detection."""

import tempfile
import unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent))

from database.db import get_connection, init_db
from services.reports import generate_excel_report, generate_csv_report
from services.risk_detector import detect_financial_anomalies
from app import app


class ReportsAndRiskTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db_path = Path(self.temp_dir.name) / 'reports_test.db'
        init_db(self.db_path)

        with get_connection(self.db_path) as conn:
            # 1. Statement doc with normal and spike transactions
            conn.execute("""INSERT INTO documents
                (filename, document_type, upload_date, processing_status, file_hash, currency)
                VALUES ('stmt.pdf', 'bank_statement', '2026-04-30', 'processed', 'hash-stmt-1', 'INR')""")
            stmt_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]

            conn.executemany("""INSERT INTO transactions
                (document_id, transaction_date, description, debit, credit, category, currency)
                VALUES (?, ?, ?, ?, ?, ?, ?)""", [
                    (stmt_id, '2026-04-01', 'Monthly Salary', None, 60000, 'Income', 'INR'),
                    (stmt_id, '2026-04-05', 'Office Supplies', 1200, None, 'Supplies', 'INR'),
                    (stmt_id, '2026-04-10', 'Coffee Shop', 350, None, 'Food', 'INR'),
                    (stmt_id, '2026-04-15', 'Bulk Server Hardware', 35000, None, 'Equipment', 'INR'),  # Outlier spike!
                ])

            # 2. Invoices with duplicate risk
            conn.execute("""INSERT INTO documents
                (filename, document_type, upload_date, processing_status, file_hash, currency)
                VALUES ('inv1.pdf', 'invoice', '2026-04-05', 'processed', 'hash-inv-1', 'INR')""")
            inv_doc1 = conn.execute('SELECT last_insert_rowid()').fetchone()[0]

            conn.execute("""INSERT INTO documents
                (filename, document_type, upload_date, processing_status, file_hash, currency)
                VALUES ('inv2.pdf', 'invoice', '2026-04-08', 'processed', 'hash-inv-2', 'INR')""")
            inv_doc2 = conn.execute('SELECT last_insert_rowid()').fetchone()[0]

            # Duplicate invoice number INV-999 uploaded twice
            conn.execute("""INSERT INTO invoices
                (document_id, invoice_number, invoice_date, vendor_name, currency, total_amount)
                VALUES (?, 'INV-999', '2026-04-02', 'Acme Corp', 'INR', 5000)""", (inv_doc1,))
            conn.execute("""INSERT INTO invoices
                (document_id, invoice_number, invoice_date, vendor_name, currency, total_amount)
                VALUES (?, 'INV-999', '2026-04-07', 'Acme Corp', 'INR', 5000)""", (inv_doc2,))

        app.config['TESTING'] = True
        self.client = app.test_client()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_excel_report_generation(self):
        """Generates valid multi-tab Excel spreadsheet stream."""
        buffer = generate_excel_report(self.db_path)
        data = buffer.getvalue()
        self.assertTrue(len(data) > 1000)
        # Check ZIP / XLSX magic signature (PK\x03\x04)
        self.assertEqual(data[:4], b'PK\x03\x04')

    def test_csv_report_generation(self):
        """Generates valid CSV export containing invoices and ledger."""
        buffer = generate_csv_report(self.db_path)
        csv_text = buffer.getvalue().decode('utf-8')
        self.assertIn('RECONCILED INVOICES', csv_text)
        self.assertIn('TRANSACTION LEDGER', csv_text)
        self.assertIn('INV-999', csv_text)
        self.assertIn('Bulk Server Hardware', csv_text)

    def test_risk_and_anomaly_detection(self):
        """Detects duplicate invoice submission and high-value expense spikes."""
        with get_connection(self.db_path) as conn:
            alerts = detect_financial_anomalies(conn)

        types = [a['type'] for a in alerts]
        self.assertIn('duplicate_invoice', types)
        self.assertIn('expense_outlier', types)

        dup_alert = next(a for a in alerts if a['type'] == 'duplicate_invoice')
        self.assertIn('INV-999', dup_alert['title'])
        self.assertEqual(dup_alert['count'], 2)

        outlier_alert = next(a for a in alerts if a['type'] == 'expense_outlier')
        self.assertEqual(outlier_alert['amount'], 35000.0)

    def test_export_endpoints(self):
        """Flask export endpoints return proper attachments."""
        with self.client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['user_email'] = 'admin@atlasfinance.com'

        # 1. Excel export
        res_excel = self.client.get('/analytics/export?format=excel')
        self.assertEqual(res_excel.status_code, 200)
        self.assertIn('spreadsheetml', res_excel.mimetype)
        self.assertTrue(res_excel.headers['Content-Disposition'].startswith('attachment'))
        self.assertTrue(res_excel.headers['Content-Disposition'].endswith('.xlsx'))

        # 2. CSV export
        res_csv = self.client.get('/analytics/export?format=csv')
        self.assertEqual(res_csv.status_code, 200)
        self.assertEqual(res_csv.mimetype, 'text/csv')
        self.assertTrue(res_csv.headers['Content-Disposition'].endswith('.csv'))


if __name__ == '__main__':
    unittest.main()
