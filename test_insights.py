"""Focused Phase 6 database-grounded question tests."""

import tempfile
import unittest
from pathlib import Path

from database.db import get_connection, init_db
from services.insights import answer_financial_question, get_financial_insights


class InsightsTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db_path = Path(self.temp_dir.name) / 'insights.db'
        init_db(self.db_path)
        with get_connection(self.db_path) as conn:
            conn.execute("""INSERT INTO documents
                (filename, document_type, upload_date, processing_status, file_hash, currency)
                VALUES ('statement.pdf', 'bank_statement', '2026-05-31', 'processed', 'insight-statement', 'INR')""")
            statement_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
            conn.executemany("""INSERT INTO transactions
                (document_id, transaction_date, description, debit, credit, currency)
                VALUES (?, ?, ?, ?, ?, ?)""", [
                    (statement_id, '2026-04-03', 'Rent', 25000, None, 'INR'),
                    (statement_id, '2026-05-02', 'Salary', None, 30000, 'INR'),
                ])
            conn.execute("""INSERT INTO documents
                (filename, document_type, upload_date, processing_status, file_hash, currency)
                VALUES ('invoice.pdf', 'invoice', '2026-04-10', 'processed', 'insight-invoice', 'INR')""")
            invoice_doc_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
            conn.execute("""INSERT INTO invoices
                (document_id, invoice_number, invoice_date, vendor_name, currency, total_amount)
                VALUES (?, 'INV-1', '2026-04-04', 'Acme Supplies', 'INR', 11600)""", (invoice_doc_id,))

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_supported_questions_use_database_values(self):
        self.assertIn('25,000.00', answer_financial_question(
            'How much did I spend in April?', self.db_path)['answer'])
        self.assertIn('30,000.00', answer_financial_question(
            'What is my total income?', self.db_path)['answer'])
        self.assertIn('1 unmatched', answer_financial_question(
            'How many invoices are unmatched?', self.db_path)['answer'])
        self.assertIn('Acme Supplies', answer_financial_question(
            'Which vendor has the highest invoice amount?', self.db_path)['answer'])

    def test_comparison_and_insights_are_data_grounded(self):
        result = answer_financial_question('Compare April and May expenses.', self.db_path)
        self.assertIn('decreased by 25,000.00', result['answer'])
        insights = get_financial_insights(self.db_path)
        self.assertTrue(insights)
        self.assertLessEqual(len(insights), 5)

    def test_unsupported_or_missing_data_does_not_guess(self):
        self.assertFalse(answer_financial_question('Should I invest?', self.db_path)['supported'])
        self.assertFalse(answer_financial_question('How much did I spend in August?', self.db_path)['supported'])


if __name__ == '__main__':
    unittest.main()