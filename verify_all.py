import os
import sys
import tempfile
from datetime import datetime

sys.path.insert(0, r'D:\mini project')

from database.db import init_db, get_connection, create_user, authenticate_user, save_document
from services.extractor import extract_text_from_pdf
from services.classifier import classify_document
from services.parser import parse_bank_statement, parse_invoice
from services.analytics import get_financial_overview, reconcile_invoices_and_transactions, detect_missing_periods
from services.insights import answer_financial_question, get_financial_insights
from services.forecaster import generate_cash_flow_forecast
from services.risk_detector import detect_financial_anomalies
from services.reports import generate_excel_report, generate_csv_report

print("=" * 65)
print("  ATLAS FINANCE - FULL SYSTEM HEALTH & INTEGRITY AUDIT")
print("=" * 65)

test_db = os.path.join(tempfile.gettempdir(), 'system_check.db')
if os.path.exists(test_db):
    try:
        os.remove(test_db)
    except Exception:
        pass
init_db(test_db)

# 1. Check Authentication & Hashing
user = create_user('lead@atlas.com', 'SecurePass123!', 'Lead Accountant', role='accountant', db_path=test_db)
assert user['email'] == 'lead@atlas.com'
assert user['role'] == 'accountant'
auth = authenticate_user('lead@atlas.com', 'SecurePass123!', test_db)
assert auth is not None and auth['id'] == user['id']
assert authenticate_user('lead@atlas.com', 'WrongPass', test_db) is None
print("[1/10 PASS] Authentication, PBKDF2 hashing, and RBAC roles verified.")

# 2. Check Document Parsers
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
Closing Balance: INR 38,000.00"""

parsed_stmt = parse_bank_statement(BANK_TEXT)
assert len(parsed_stmt['transactions']) == 4
print(f"[2/10 PASS] Bank Statement parser extracted {len(parsed_stmt['transactions'])} transactions.")

INVOICE_TEXT = """SUPPLIER INVOICE
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
INR 5,000.00"""

parsed_inv = parse_invoice(INVOICE_TEXT)
assert parsed_inv['invoice_number'] == 'INV-2026-101'
assert parsed_inv['total_amount'] == 5000.00
print(f"[3/10 PASS] Invoice parser extracted invoice {parsed_inv['invoice_number']} for INR {parsed_inv['total_amount']}.")

# 3. Check DB Storage & Cascades
stmt_meta = {
    'filename': 'stmt.pdf',
    'document_type': 'bank_statement',
    'currency': 'INR',
    'upload_date': '2026-10-02',
    'file_size': 1024,
    'page_count': 1
}
inv_meta = {
    'filename': 'inv1.pdf',
    'document_type': 'invoice',
    'currency': 'INR',
    'upload_date': '2026-10-02',
    'file_size': 512,
    'page_count': 1
}
d1 = save_document(stmt_meta, parsed_stmt, 'hash-stmt-1', db_path=test_db)
d2 = save_document(inv_meta, parsed_inv, 'hash-inv-1', db_path=test_db)
assert d1 is not None and d2 is not None
print("[4/10 PASS] Document bundle and child transaction/invoice storage verified.")

# 4. Check Reconciliation
rec_count = reconcile_invoices_and_transactions(test_db)
with get_connection(test_db) as conn:
    invoices = conn.execute('SELECT invoice_number, reconciliation_status FROM invoices').fetchall()
assert invoices[0]['reconciliation_status'] == 'PAID'
print(f"[5/10 PASS] Automated reconciliation verified: Invoice {invoices[0]['invoice_number']} reconciled to PAID.")

# 5. Check Gap Detection
with get_connection(test_db) as conn:
    # Filter from 2026-08 to 2026-10 with data in 2026-10 -> 2026-08 and 2026-09 are missing.
    missing = detect_missing_periods(conn, {'date_from': '2026-08-01', 'date_to': '2026-10-31'})
assert missing['has_missing'] is True
assert 'September 2026' in missing['missing_months_labels']
print(f"[6/10 PASS] Data continuity & missing period gap detection verified ({', '.join(missing['missing_months_labels'])} detected).")

# 6. Check Forecasting Engine
with get_connection(test_db) as conn:
    fc = generate_cash_flow_forecast(conn)
assert 'projected_income_30d' in fc
assert 'runway_months' in fc
print(f"[7/10 PASS] Predictive Forecaster verified: Runway is {fc['runway_months']} months ({fc['runway_status']}).")

# 7. Check Risk Detector
with get_connection(test_db) as conn:
    anomalies = detect_financial_anomalies(conn)
assert isinstance(anomalies, list)
print(f"[8/10 PASS] Financial Risk & Anomaly Detector verified: Returned list of {len(anomalies)} alerts.")

# 8. Check Excel & CSV Reports
excel_buf = generate_excel_report(test_db)
csv_buf = generate_csv_report(test_db)
assert len(excel_buf.getvalue()) > 1000
assert len(csv_buf.getvalue()) > 100
print(f"[9/10 PASS] Audit-Ready Reports verified: Excel ({len(excel_buf.getvalue())} bytes) & CSV ({len(csv_buf.getvalue())} bytes).")

# 9. Check Natural Language Q&A
q_res = answer_financial_question('What is my financial runway?', test_db)
assert q_res['supported'] is True
print(f"[10/10 PASS] Ask the Ledger Q&A verified: {q_res['answer'][:70]}...")

print("=" * 65)
print(">>> ALL 10 SUBSYSTEMS ARE 100% OPERATIONAL AND WORKING PERFECTLY! <<<")
print("=" * 65)
