"""Financial report generator producing audit-ready Excel and CSV files."""

import io
import csv
import sys
from datetime import datetime
from pathlib import Path
import xlsxwriter

# Ensure project root is in sys.path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from database.db import get_connection
from config import DATABASE_PATH
from services.analytics import (
    get_financial_overview,
    get_reconciled_invoices,
    _filter_values,
    _transaction_where,
)


def generate_excel_report(db_path=DATABASE_PATH, filters=None, user_id=None):
    """
    Generate an audit-ready, multi-tab Excel workbook containing:
    1. Executive Summary & KPIs
    2. Invoice Reconciliation Schedule
    3. Transaction Ledger
    4. Category Spending Breakdown
    """
    filters = _filter_values(filters)
    overview = get_financial_overview(db_path, filters, user_id=user_id)
    invoices = get_reconciled_invoices(db_path, filters, user_id=user_id)

    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output, {'in_memory': True})

    # Color Palette & Styles
    brand_header = workbook.add_format({
        'bold': True, 'font_size': 14, 'bg_color': '#1e3a8a',
        'font_color': '#ffffff', 'align': 'center', 'valign': 'vcenter'
    })
    sheet_header = workbook.add_format({
        'bold': True, 'font_size': 11, 'bg_color': '#0f172a',
        'font_color': '#ffffff', 'align': 'left', 'valign': 'vcenter'
    })
    th_format = workbook.add_format({
        'bold': True, 'font_size': 10, 'bg_color': '#2563eb',
        'font_color': '#ffffff', 'align': 'center', 'border': 1
    })
    label_format = workbook.add_format({
        'bold': True, 'font_size': 10, 'font_color': '#334155'
    })
    cell_format = workbook.add_format({'font_size': 10, 'font_color': '#0f172a', 'border': 1})
    date_format = workbook.add_format({'font_size': 10, 'align': 'center', 'border': 1})
    currency_format = workbook.add_format({
        'font_size': 10, 'num_format': '₹#,##0.00', 'align': 'right', 'border': 1
    })
    total_currency_format = workbook.add_format({
        'bold': True, 'font_size': 10, 'num_format': '₹#,##0.00',
        'bg_color': '#f1f5f9', 'border': 1
    })
    badge_paid = workbook.add_format({
        'bold': True, 'font_size': 9, 'bg_color': '#dcfce7',
        'font_color': '#166534', 'align': 'center', 'border': 1
    })
    badge_pending = workbook.add_format({
        'bold': True, 'font_size': 9, 'bg_color': '#fef3c7',
        'font_color': '#b45309', 'align': 'center', 'border': 1
    })

    # =========================================================================
    # Tab 1: Executive Summary
    # =========================================================================
    ws1 = workbook.add_worksheet('Executive Summary')
    ws1.set_column('A:A', 30)
    ws1.set_column('B:B', 24)
    ws1.set_column('C:D', 20)

    ws1.merge_range('A1:D1', 'ATLAS FINANCE - FINANCIAL AUDIT REPORT', brand_header)
    ws1.write('A3', 'Report Generation Date:', label_format)
    ws1.write('B3', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    ws1.write('A4', 'Workspace Currency:', label_format)
    ws1.write('B4', overview.get('filters', {}).get('currency') or 'INR')
    ws1.write('A5', 'Date Filter Range:', label_format)
    start_dt = overview.get('filters', {}).get('date_from') or 'Earliest Available'
    end_dt = overview.get('filters', {}).get('date_to') or 'Latest Available'
    ws1.write('B5', f"{start_dt} to {end_dt}")

    ws1.merge_range('A7:B7', 'CORE FINANCIAL METRICS', sheet_header)
    kpis = [
        ('Total Verified Income', overview['total_income']),
        ('Total Expenses Paid', overview['total_expenses']),
        ('Net Cash Flow', overview['net_cash_flow']),
        ('Total Invoiced Amount', overview['total_invoiced']),
        ('Matched / Settled Invoices', overview['matched_amount']),
        ('Pending Unsettled Liabilities', overview['unmatched_amount']),
        ('Total Taxes Recorded', overview['total_tax']),
    ]
    for row_idx, (kpi_name, kpi_val) in enumerate(kpis, start=8):
        ws1.write(f'A{row_idx}', kpi_name, label_format)
        ws1.write(f'B{row_idx}', kpi_val, currency_format)

    ws1.merge_range('A16:B16', 'OPERATIONAL VOLUME', sheet_header)
    volumes = [
        ('Bank Statement Transactions', overview['transaction_count']),
        ('Credit (Income) Transactions', overview['credit_count']),
        ('Debit (Expense) Transactions', overview['debit_count']),
        ('Total Invoices Ingested', overview['invoice_count']),
        ('Paid / Reconciled Invoices', overview['paid_invoices']),
        ('Pending Supplier Invoices', overview['pending_invoices']),
    ]
    for row_idx, (v_name, v_count) in enumerate(volumes, start=17):
        ws1.write(f'A{row_idx}', v_name, label_format)
        ws1.write(f'B{row_idx}', v_count, cell_format)

    # =========================================================================
    # Tab 2: Reconciliation Schedule
    # =========================================================================
    ws2 = workbook.add_worksheet('Reconciliation Schedule')
    ws2.set_column('A:A', 18)
    ws2.set_column('B:B', 28)
    ws2.set_column('C:D', 14)
    ws2.set_column('E:F', 16)
    ws2.set_column('G:G', 14)
    ws2.set_column('H:H', 16)
    ws2.set_column('I:I', 32)

    headers_ws2 = [
        'Invoice #', 'Vendor Name', 'Invoice Date', 'Due Date',
        'Total Amount', 'Tax', 'Status', 'Paid Date', 'Bank Match Remark'
    ]
    for col_idx, h in enumerate(headers_ws2):
        ws2.write(0, col_idx, h, th_format)

    for row_idx, inv in enumerate(invoices, start=1):
        ws2.write(row_idx, 0, inv.get('invoice_number') or 'N/A', cell_format)
        ws2.write(row_idx, 1, inv.get('vendor_name') or 'Unknown Vendor', cell_format)
        ws2.write(row_idx, 2, inv.get('invoice_date') or '', date_format)
        ws2.write(row_idx, 3, inv.get('due_date') or '', date_format)
        ws2.write(row_idx, 4, float(inv.get('total_amount') or 0), currency_format)
        ws2.write(row_idx, 5, float(inv.get('tax') or 0), currency_format)

        status = inv.get('reconciliation_status', 'PENDING')
        ws2.write(row_idx, 6, status, badge_paid if status == 'PAID' else badge_pending)
        ws2.write(row_idx, 7, inv.get('paid_date') or '-', date_format)
        ws2.write(row_idx, 8, inv.get('paid_description') or '-', cell_format)

    # =========================================================================
    # Tab 3: Transaction Ledger
    # =========================================================================
    ws3 = workbook.add_worksheet('Transaction Ledger')
    ws3.set_column('A:A', 14)
    ws3.set_column('B:B', 36)
    ws3.set_column('C:C', 10)
    ws3.set_column('D:D', 16)
    ws3.set_column('E:E', 22)
    ws3.set_column('F:F', 10)

    headers_ws3 = ['Date', 'Description', 'Type', 'Amount', 'Category', 'Currency']
    for col_idx, h in enumerate(headers_ws3):
        ws3.write(0, col_idx, h, th_format)

    with get_connection(db_path) as conn:
        tx_where, tx_params = _transaction_where(filters, user_id=user_id)
        tx_rows = conn.execute("""
            SELECT t.transaction_date, t.description,
                   CASE WHEN t.credit > 0 THEN 'Credit' ELSE 'Debit' END AS type,
                   COALESCE(t.credit, t.debit, 0) AS amount,
                   COALESCE(t.category, 'Uncategorized') AS category,
                   t.currency
            FROM transactions t
            JOIN documents d ON d.id = t.document_id
            WHERE """ + tx_where + " ORDER BY t.transaction_date DESC, t.id DESC", tx_params).fetchall()

        for row_idx, r in enumerate(tx_rows, start=1):
            ws3.write(row_idx, 0, r['transaction_date'] or '', date_format)
            ws3.write(row_idx, 1, r['description'] or '', cell_format)
            ws3.write(row_idx, 2, r['type'], cell_format)
            ws3.write(row_idx, 3, float(r['amount']), currency_format)
            ws3.write(row_idx, 4, r['category'], cell_format)
            ws3.write(row_idx, 5, r['currency'] or 'INR', cell_format)

    # =========================================================================
    # Tab 4: Expense Categories
    # =========================================================================
    ws4 = workbook.add_worksheet('Expense Categories')
    ws4.set_column('A:A', 26)
    ws4.set_column('B:B', 18)
    ws4.set_column('C:C', 16)

    ws4.write(0, 0, 'Category', th_format)
    ws4.write(0, 1, 'Total Spent', th_format)
    ws4.write(0, 2, '% of Expenses', th_format)

    total_expense = overview['total_expenses'] or 1.0
    for row_idx, cat in enumerate(overview['categories'], start=1):
        pct = (cat['total'] / total_expense) * 100.0
        ws4.write(row_idx, 0, cat['category'], cell_format)
        ws4.write(row_idx, 1, cat['total'], currency_format)
        ws4.write(row_idx, 2, f"{pct:.1f}%", cell_format)

    workbook.close()
    output.seek(0)
    return output


def generate_csv_report(db_path=DATABASE_PATH, filters=None, user_id=None):
    """Generate a clean CSV export of the reconciled transactions & invoices."""
    filters = _filter_values(filters)
    invoices = get_reconciled_invoices(db_path, filters, user_id=user_id)

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(['--- RECONCILED INVOICES ---'])
    writer.writerow([
        'Invoice Number', 'Vendor Name', 'Invoice Date', 'Due Date',
        'Total Amount', 'Tax', 'Status', 'Paid Date', 'Paid Bank Remark'
    ])
    for inv in invoices:
        writer.writerow([
            inv.get('invoice_number', ''),
            inv.get('vendor_name', ''),
            inv.get('invoice_date', ''),
            inv.get('due_date', ''),
            inv.get('total_amount', 0),
            inv.get('tax', 0),
            inv.get('reconciliation_status', 'PENDING'),
            inv.get('paid_date', ''),
            inv.get('paid_description', ''),
        ])

    writer.writerow([])
    writer.writerow(['--- TRANSACTION LEDGER ---'])
    writer.writerow(['Date', 'Description', 'Type', 'Amount', 'Category', 'Currency'])

    with get_connection(db_path) as conn:
        tx_where, tx_params = _transaction_where(filters, user_id=user_id)
        tx_rows = conn.execute("""
            SELECT t.transaction_date, t.description,
                   CASE WHEN t.credit > 0 THEN 'Credit' ELSE 'Debit' END AS type,
                   COALESCE(t.credit, t.debit, 0) AS amount,
                   COALESCE(t.category, 'Uncategorized') AS category,
                   t.currency
            FROM transactions t
            JOIN documents d ON d.id = t.document_id
            WHERE """ + tx_where + " ORDER BY t.transaction_date DESC, t.id DESC", tx_params).fetchall()

        for r in tx_rows:
            writer.writerow([
                r['transaction_date'], r['description'], r['type'],
                r['amount'], r['category'], r['currency']
            ])

    output.seek(0)
    return io.BytesIO(output.getvalue().encode('utf-8'))
