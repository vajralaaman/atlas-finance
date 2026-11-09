"""Regression tests for PDF-shaped parsing, storage, analytics, and reconciliation."""

import tempfile
import unittest
from pathlib import Path

from database.db import get_connection, init_db, save_document
from services.analytics import get_financial_overview, reconcile_invoices_and_transactions
from services.parser import parse_bank_statement, parse_invoice


BANK_TEXT = """SAMPLE BANK STATEMENT
Demo Bank | Account Holder: Atlas Demo Shop
Account Number: XXXX-XXXX-1234 | Currency: INR
Statement Period: 01 October 2026 to 07 October 2026
Opening Balance: INR 25,000.00
Date
Description
Debit (INR)
Credit (INR)
Balance (INR)
01-10-2026
Customer Deposit
-
12,000.00
37,000.00
02-10-2026
ABC Electronics Pvt Ltd
5,000.00
-
32,000.00
03-10-2026
Customer UPI Payment
-
8,500.00
40,500.00
04-10-2026
City Electricals
2,500.00
-
38,000.00
05-10-2026
Shop Rent
6,000.00
-
32,000.00
06-10-2026
Customer Deposit
-
4,000.00
36,000.00
Closing Balance: INR 36,000.00"""


class DocumentPipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db_path = Path(self.temp_dir.name) / 'pipeline.db'
        init_db(self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_bank_statement_parser_reads_columnar_rows(self):
        parsed = parse_bank_statement(BANK_TEXT)
        transactions = parsed['transactions']
        self.assertEqual(len(transactions), 6)
        self.assertEqual(sum(row['credit'] or 0 for row in transactions), 24500.0)
        self.assertEqual(sum(row['debit'] or 0 for row in transactions), 13500.0)
        self.assertEqual(parsed['statement_information']['opening_balance'], 25000.0)
        self.assertEqual(parsed['statement_information']['closing_balance'], 36000.0)
        self.assertEqual(transactions[1]['description'], 'ABC Electronics Pvt Ltd')
        self.assertEqual(transactions[1]['debit'], 5000.0)

    def test_invoice_parser_reads_labeled_multiline_fields(self):
        parsed = parse_invoice("""SUPPLIER INVOICE
ABC Electronics Pvt Ltd
Invoice Number: INV-2026-101
Invoice Date: 02 October 2026
Bill To: Atlas Demo Shop
Currency: INR
Subtotal
INR 5,000.00
Tax
INR 0.00
Total Due
INR 5,000.00""")
        self.assertEqual(parsed['invoice_number'], 'INV-2026-101')
        self.assertEqual(parsed['vendor_name'], 'ABC Electronics Pvt Ltd')
        self.assertEqual(parsed['invoice_date'], '2026-10-02')
        self.assertEqual(parsed['subtotal'], 5000.0)
        self.assertEqual(parsed['total_amount'], 5000.0)
        self.assertEqual(parsed['items'], [])

    def test_invoice_parser_reads_columnar_items(self):
        parsed = parse_invoice("""SUPPLIER INVOICE
ABC Electronics Pvt Ltd
Invoice Number: INV-2026-101
Invoice Date: 02 October 2026
Items / Services
Description
Quantity
Unit Price (INR)
Line Total (INR)
Shop accessories
2
1,500.00
3,000.00
Cables and adapters
4
500.00
2,000.00
Subtotal
INR 5,000.00
Total Due
INR 5,000.00""")
        self.assertEqual(len(parsed['items']), 2)
        self.assertEqual(parsed['items'][0]['line_total'], 3000.0)

    def test_storage_analytics_filters_and_reconciliation(self):
        bank = parse_bank_statement(BANK_TEXT)
        bank_doc = {
            'filename': 'statement.pdf', 'document_type': 'bank_statement',
            'upload_date': '2026-10-07', 'processing_status': 'processed',
            'extracted_text': BANK_TEXT,
        }
        bank_bundle, _ = save_document(bank_doc, bank, 'bank-hash', self.db_path)
        invoice_values = [
            ('INV-2026-101', 'ABC Electronics Pvt Ltd', '2026-10-02', 5000.0),
            ('INV-2026-102', 'City Electricals', '2026-10-04', 2500.0),
            ('INV-2026-103', 'Sunrise Packaging', '2026-10-07', 1800.0),
        ]
        for number, vendor, invoice_date, total in invoice_values:
            invoice = {
                'invoice_number': number, 'invoice_date': invoice_date,
                'vendor_name': vendor, 'customer_name': 'Atlas Demo Shop',
                'currency': 'INR', 'subtotal': total, 'tax': 0.0,
                'discount': 0.0, 'total_amount': total, 'items': [],
            }
            save_document(
                {'filename': f'{number}.pdf', 'document_type': 'invoice',
                 'upload_date': invoice_date, 'processing_status': 'processed',
                 'extracted_text': ''}, invoice, number, self.db_path,
            )

        with get_connection(self.db_path) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM transactions').fetchone()[0], 6)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM invoices').fetchone()[0], 3)

        reconcile_invoices_and_transactions(self.db_path)
        overview = get_financial_overview(self.db_path, {'month': '2026-10', 'currency': 'INR'})
        self.assertEqual(overview['total_income'], 24500.0)
        self.assertEqual(overview['total_expenses'], 13500.0)
        self.assertEqual(overview['transaction_count'], 6)
        self.assertEqual(overview['paid_invoices'], 2)
        self.assertEqual(overview['pending_invoices'], 1)
        self.assertEqual(overview['total_invoiced'], 9300.0)
        self.assertEqual(overview['monthly_trends'][0]['month'], '2026-10')
        self.assertEqual(len(overview['categories']), 3)


if __name__ == '__main__':
    unittest.main()
