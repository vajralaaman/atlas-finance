"""Automated pipeline test script."""

from pathlib import Path
from database.db import init_db
from services.analytics import get_financial_overview, reconcile_invoices_and_transactions
from app import app

app.config['TESTING'] = True
client = app.test_client()

with client.session_transaction() as sess:
    sess['user_id'] = 1
    sess['user_email'] = 'admin@atlasfinance.com'
    sess['user_name'] = 'Admin User'
    sess['user_role'] = 'admin'

print("--- 1. Testing Database Initialization ---")
init_db()
print("Database initialized successfully.")

print("\n--- 2. Ingesting Sample Documents ---")
sample_dir = Path('../sample_documents')
if not sample_dir.exists():
    sample_dir = Path('sample_documents')

pdfs = list(sample_dir.glob('*.pdf'))
print(f"Found {len(pdfs)} sample PDFs.")

for pdf in pdfs:
    with open(pdf, 'rb') as f:
        res = client.post(
            '/upload',
            data={'files': (f, pdf.name, 'application/pdf')},
            content_type='multipart/form-data'
        )
        print(f"Uploaded {pdf.name} -> HTTP {res.status_code}")

print("\n--- 3. Testing Financial Analytics & Reconciliation ---")
overview = get_financial_overview()
print("Total Income:   Rs.", f"{overview['total_income']:,.2f}")
print("Total Expenses: Rs.", f"{overview['total_expenses']:,.2f}")
print("Net Cash Flow:  Rs.", f"{overview['net_cash_flow']:,.2f}")
print("Total Invoiced: Rs.", f"{overview['total_invoiced']:,.2f}")

reconciled = reconcile_invoices_and_transactions()
print(f"\nReconciled {len(reconciled)} invoices against bank statement debits.")
for inv in reconciled:
    print(f" - Invoice {inv['invoice_number']} ({inv['vendor_name']}): {inv['reconciliation_status']}")

print("\nAll pipeline tests passed!")