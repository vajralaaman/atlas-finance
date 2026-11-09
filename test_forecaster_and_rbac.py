"""Unit tests for Predictive Cash Flow Forecasting and Role-Based Access Control (RBAC)."""

import tempfile
import unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent))

from database.db import get_connection, init_db, create_user, authenticate_user
from services.forecaster import generate_cash_flow_forecast
from services.insights import answer_financial_question
from app import app


class ForecasterAndRBACTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db_path = Path(self.temp_dir.name) / 'forecast_test.db'
        init_db(self.db_path)

        with get_connection(self.db_path) as conn:
            # Multi-month statement transactions to test regression forecasting
            conn.execute("""INSERT INTO documents
                (filename, document_type, upload_date, processing_status, file_hash, currency)
                VALUES ('stmt.pdf', 'bank_statement', '2026-04-30', 'processed', 'hash-f-1', 'INR')""")
            stmt_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]

            conn.executemany("""INSERT INTO transactions
                (document_id, transaction_date, description, debit, credit, category, currency)
                VALUES (?, ?, ?, ?, ?, ?, ?)""", [
                    # Month 1 (April 2026): Income 40k, Expenses 15k
                    (stmt_id, '2026-04-01', 'Salary', None, 40000, 'Income', 'INR'),
                    (stmt_id, '2026-04-05', 'Rent', 15000, None, 'Housing', 'INR'),
                    # Month 2 (May 2026): Income 45k, Expenses 16k
                    (stmt_id, '2026-05-01', 'Salary', None, 45000, 'Income', 'INR'),
                    (stmt_id, '2026-05-05', 'Rent', 16000, None, 'Housing', 'INR'),
                    # Month 3 (June 2026): Income 50k, Expenses 17k
                    (stmt_id, '2026-06-01', 'Salary', None, 50000, 'Income', 'INR'),
                    (stmt_id, '2026-06-05', 'Rent', 17000, None, 'Housing', 'INR'),
                ])

        app.config['TESTING'] = True
        self.client = app.test_client()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_predictive_forecaster_regression(self):
        """Linear regression accurately models 30d and 60d projections."""
        with get_connection(self.db_path) as conn:
            fc = generate_cash_flow_forecast(conn)

        self.assertTrue(fc['has_forecast'])
        self.assertEqual(fc['next_month_label'], 'July 2026')
        self.assertEqual(fc['second_month_label'], 'August 2026')

        # Since income was 40k, 45k, 50k (slope +5k) -> July should be 55,000.0
        self.assertEqual(fc['projected_income_30d'], 55000.0)
        # August should be 60,000.0
        self.assertEqual(fc['projected_income_60d'], 60000.0)

        # Expenses were 15k, 16k, 17k (slope +1k) -> July should be 18,000.0
        self.assertEqual(fc['projected_expense_30d'], 18000.0)

        # Projected Net
        self.assertEqual(fc['projected_net_30d'], 37000.0)
        self.assertTrue(fc['runway_months'] > 0)

    def test_runway_and_forecast_natural_language_qa(self):
        """Ask the Ledger answers forecasting and runway queries."""
        ans_runway = answer_financial_question("What is my financial runway?", self.db_path)
        self.assertTrue(ans_runway['supported'])
        self.assertIn('runway', ans_runway['answer'].lower())

        ans_fc = answer_financial_question("What is my projected cash flow?", self.db_path)
        self.assertTrue(ans_fc['supported'])
        self.assertIn('projected', ans_fc['answer'].lower())

    def test_rbac_user_creation_and_auth(self):
        """User accounts store roles (admin, accountant, auditor)."""
        auditor = create_user('auditor@company.com', 'Pass123456', 'Auditor User', role='auditor', db_path=self.db_path)
        self.assertEqual(auditor['role'], 'auditor')

        auth_user = authenticate_user('auditor@company.com', 'Pass123456', self.db_path)
        self.assertIsNotNone(auth_user)
        self.assertEqual(auth_user['role'], 'auditor')


if __name__ == '__main__':
    unittest.main()
