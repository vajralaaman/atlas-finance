"""Database-backed financial analytics and invoice reconciliation."""

import sys
from pathlib import Path

# Ensure project root is in sys.path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from datetime import datetime
from database.db import get_connection
from config import DATABASE_PATH


def _filter_values(filters=None):
    filters = filters or {}
    return {key: (filters.get(key) or '').strip() for key in (
        'date_from', 'date_to', 'month', 'year', 'document_type', 'currency'
    )}


def _transaction_where(filters, user_id=None):
    clauses, params = [], []
    if user_id is not None:
        clauses.append('d.user_id = ?')
        params.append(user_id)
    if filters.get('date_from'):
        clauses.append('t.transaction_date >= ?')
        params.append(filters['date_from'])
    if filters.get('date_to'):
        clauses.append('t.transaction_date <= ?')
        params.append(filters['date_to'])
    if filters.get('month'):
        clauses.append('SUBSTR(t.transaction_date, 1, 7) = ?')
        params.append(filters['month'])
    if filters.get('year'):
        clauses.append('SUBSTR(t.transaction_date, 1, 4) = ?')
        params.append(filters['year'])
    if filters.get('document_type'):
        clauses.append('d.document_type = ?')
        params.append(filters['document_type'])
    if filters.get('currency'):
        clauses.append('t.currency = ?')
        params.append(filters['currency'])
    return ' AND '.join(clauses) or '1 = 1', params


def _invoice_where(filters, user_id=None):
    clauses, params = [], []
    if user_id is not None:
        clauses.append('d.user_id = ?')
        params.append(user_id)
    if filters.get('date_from'):
        clauses.append('i.invoice_date >= ?')
        params.append(filters['date_from'])
    if filters.get('date_to'):
        clauses.append('i.invoice_date <= ?')
        params.append(filters['date_to'])
    if filters.get('month'):
        clauses.append('SUBSTR(i.invoice_date, 1, 7) = ?')
        params.append(filters['month'])
    if filters.get('year'):
        clauses.append('SUBSTR(i.invoice_date, 1, 4) = ?')
        params.append(filters['year'])
    if filters.get('document_type'):
        clauses.append('d.document_type = ?')
        params.append(filters['document_type'])
    if filters.get('currency'):
        clauses.append('i.currency = ?')
        params.append(filters['currency'])
    return ' AND '.join(clauses) or '1 = 1', params


def _format_month_name(ym_str):
    """Convert '2026-02' to 'February 2026'."""
    try:
        dt = datetime.strptime(ym_str, '%Y-%m')
        return dt.strftime('%B %Y')
    except Exception:
        return ym_str


def _generate_months_range(start_ym, end_ym):
    """Generate list of 'YYYY-MM' strings between start_ym and end_ym inclusive."""
    try:
        start_year, start_month = map(int, start_ym.split('-'))
        end_year, end_month = map(int, end_ym.split('-'))
    except Exception:
        return []

    if (start_year, start_month) > (end_year, end_month):
        return []

    months = []
    curr_y, curr_m = start_year, start_month
    while (curr_y, curr_m) <= (end_year, end_month):
        months.append(f'{curr_y:04d}-{curr_m:02d}')
        curr_m += 1
        if curr_m > 12:
            curr_m = 1
            curr_y += 1
    return months


def _get_present_months(conn, filters=None, user_id=None):
    """Return set of 'YYYY-MM' strings that contain transactions or invoices."""
    filters = _filter_values(filters)
    tx_clauses = ['t.transaction_date IS NOT NULL']
    tx_params = []
    inv_clauses = ['i.invoice_date IS NOT NULL']
    inv_params = []

    if user_id is not None:
        tx_clauses.append('d.user_id = ?')
        tx_params.append(user_id)
        inv_clauses.append('d.user_id = ?')
        inv_params.append(user_id)

    if filters['currency']:
        tx_clauses.append('t.currency = ?')
        tx_params.append(filters['currency'])
        inv_clauses.append('i.currency = ?')
        inv_params.append(filters['currency'])

    if filters['document_type']:
        tx_clauses.append('d.document_type = ?')
        tx_params.append(filters['document_type'])
        inv_clauses.append('d.document_type = ?')
        inv_params.append(filters['document_type'])

    query = f"""
        SELECT DISTINCT SUBSTR(t.transaction_date, 1, 7) AS ym
        FROM transactions t
        JOIN documents d ON d.id = t.document_id
        WHERE {' AND '.join(tx_clauses)}
        UNION
        SELECT DISTINCT SUBSTR(i.invoice_date, 1, 7) AS ym
        FROM invoices i
        JOIN documents d ON d.id = i.document_id
        WHERE {' AND '.join(inv_clauses)}
    """
    rows = conn.execute(query, tx_params + inv_params).fetchall()
    return {row['ym'] for row in rows if row['ym']}


def detect_missing_periods(conn, filters=None, user_id=None):
    """
    Detect missing months within a filtered date duration.

    Identifies intermediate or range gap months (e.g. filtered Jan to Apr, but Feb is missing)
    so the dashboard can notify the user to upload missing statements.
    """
    filters = _filter_values(filters)
    present_months = _get_present_months(conn, filters, user_id=user_id)

    start_ym = None
    end_ym = None

    if filters['date_from'] and filters['date_to']:
        start_ym = filters['date_from'][:7]
        end_ym = filters['date_to'][:7]
    elif filters['date_from'] and present_months:
        start_ym = filters['date_from'][:7]
        end_ym = max(present_months)
    elif filters['date_to'] and present_months:
        start_ym = min(present_months)
        end_ym = filters['date_to'][:7]
    elif filters['year'] and present_months:
        year_months = [m for m in present_months if m.startswith(filters['year'])]
        if len(year_months) >= 2:
            start_ym = min(year_months)
            end_ym = max(year_months)

    if not start_ym or not end_ym or start_ym >= end_ym:
        return {
            'has_missing': False,
            'missing_months': [],
            'missing_months_labels': [],
            'start_period': '',
            'end_period': '',
            'message': '',
            'missing_count': 0,
            'is_middle_gap': False,
        }

    expected_months = _generate_months_range(start_ym, end_ym)
    if len(expected_months) < 2:
        return {
            'has_missing': False,
            'missing_months': [],
            'missing_months_labels': [],
            'start_period': '',
            'end_period': '',
            'message': '',
            'missing_count': 0,
            'is_middle_gap': False,
        }

    missing_months = [m for m in expected_months if m not in present_months]
    if not missing_months:
        return {
            'has_missing': False,
            'missing_months': [],
            'missing_months_labels': [],
            'start_period': _format_month_name(start_ym),
            'end_period': _format_month_name(end_ym),
            'message': '',
            'missing_count': 0,
            'is_middle_gap': False,
        }

    missing_labels = [_format_month_name(m) for m in missing_months]
    start_label = _format_month_name(start_ym)
    end_label = _format_month_name(end_ym)

    if len(missing_labels) == 1:
        gap_text = missing_labels[0]
    elif len(missing_labels) == 2:
        gap_text = f'{missing_labels[0]} and {missing_labels[1]}'
    else:
        gap_text = f"{', '.join(missing_labels[:-1])}, and {missing_labels[-1]}"

    is_middle = any(start_ym < m < end_ym for m in missing_months)
    message = f'Missing financial records detected for {gap_text} within the selected period ({start_label} to {end_label}).'

    return {
        'has_missing': True,
        'missing_months': missing_months,
        'missing_months_labels': missing_labels,
        'start_period': start_label,
        'end_period': end_label,
        'message': message,
        'missing_count': len(missing_months),
        'is_middle_gap': is_middle,
    }


def get_financial_overview(db_path=DATABASE_PATH, filters=None, user_id=None):
    """Return dashboard metrics calculated only from stored SQLite records scoped to user."""
    filters = _filter_values(filters)
    with get_connection(db_path) as conn:
        tx_where, tx_params = _transaction_where(filters, user_id=user_id)
        inv_where, inv_params = _invoice_where(filters, user_id=user_id)
        tx_stats = conn.execute("""
            SELECT COALESCE(SUM(t.credit), 0) AS total_income,
                   COALESCE(SUM(t.debit), 0) AS total_expenses,
                   COUNT(t.id) AS transaction_count,
                   SUM(CASE WHEN t.credit > 0 THEN 1 ELSE 0 END) AS credit_count,
                   SUM(CASE WHEN t.debit > 0 THEN 1 ELSE 0 END) AS debit_count,
                   AVG(CASE WHEN t.credit > 0 THEN t.credit END) AS average_income,
                   AVG(CASE WHEN t.debit > 0 THEN t.debit END) AS average_expense,
                   AVG(CASE WHEN t.credit > 0 THEN t.credit WHEN t.debit > 0 THEN t.debit END) AS average_transaction,
                   MAX(t.credit) AS highest_credit, MAX(t.debit) AS highest_debit
            FROM transactions t JOIN documents d ON d.id = t.document_id
            WHERE """ + tx_where, tx_params).fetchone()

        total_income = float(tx_stats['total_income'])
        total_expenses = float(tx_stats['total_expenses'])
        net_cash_flow = total_income - total_expenses

        inv_stats = conn.execute("""
            SELECT COUNT(i.id) AS invoice_count,
                   COALESCE(SUM(i.total_amount), 0) AS total_invoiced,
                   AVG(i.total_amount) AS average_invoice,
                   MAX(i.total_amount) AS highest_invoice,
                   COALESCE(SUM(i.tax), 0) AS total_tax,
                   COALESCE(SUM(i.discount), 0) AS total_discount,
                   SUM(CASE WHEN i.reconciliation_status = 'PAID' THEN 1 ELSE 0 END) AS paid_count,
                   COALESCE(SUM(CASE WHEN i.reconciliation_status = 'PAID' THEN i.total_amount ELSE 0 END), 0) AS matched_amount
            FROM invoices i JOIN documents d ON d.id = i.document_id
            WHERE """ + inv_where, inv_params).fetchone()

        total_invoiced = float(inv_stats['total_invoiced'])
        invoice_count = int(inv_stats['invoice_count'])
        paid_invoices = int(inv_stats['paid_count'] or 0)

        monthly_rows = conn.execute("""
            SELECT SUBSTR(t.transaction_date, 1, 7) AS month,
                   COALESCE(SUM(t.credit), 0) AS income,
                   COALESCE(SUM(t.debit), 0) AS expenses
            FROM transactions t JOIN documents d ON d.id = t.document_id
            WHERE t.transaction_date IS NOT NULL AND """ + tx_where + " GROUP BY month ORDER BY month ASC", tx_params).fetchall()

        monthly_trends = []
        for r in monthly_rows:
            inc = float(r['income'])
            exp = float(r['expenses'])
            monthly_trends.append({
                'month': r['month'],
                'income': inc,
                'expenses': exp,
                'net': inc - exp
            })

        category_rows = conn.execute("""
            SELECT COALESCE(t.category, 'Uncategorized') AS category,
                   COALESCE(SUM(t.debit), 0) AS total_spent
            FROM transactions t JOIN documents d ON d.id = t.document_id
            WHERE t.debit > 0 AND """ + tx_where + " GROUP BY category ORDER BY total_spent DESC", tx_params).fetchall()

        categories = [{'category': r['category'], 'total': float(r['total_spent'])} for r in category_rows]
        transaction_rows = conn.execute("""
            SELECT t.transaction_date, t.description,
                   CASE WHEN t.credit > 0 THEN 'Credit' ELSE 'Debit' END AS type,
                   COALESCE(t.credit, t.debit) AS amount, t.currency
            FROM transactions t JOIN documents d ON d.id = t.document_id
            WHERE """ + tx_where + " ORDER BY amount DESC, t.transaction_date DESC LIMIT 10", tx_params).fetchall()
        expense_rows = conn.execute("""
            SELECT t.transaction_date, t.description, 'Debit' AS type,
                   t.debit AS amount, t.currency
            FROM transactions t JOIN documents d ON d.id = t.document_id
            WHERE t.debit > 0 AND """ + tx_where + " ORDER BY t.debit DESC, t.transaction_date DESC LIMIT 5", tx_params).fetchall()
        recent_expense_rows = conn.execute("""
            SELECT t.transaction_date, t.description, t.debit AS amount,
                   t.currency, COALESCE(t.category, 'Uncategorized') AS category
            FROM transactions t JOIN documents d ON d.id = t.document_id
            WHERE t.debit > 0 AND """ + tx_where + " ORDER BY t.transaction_date DESC, t.id DESC LIMIT 6", tx_params).fetchall()
        vendor_rows = conn.execute("""
            SELECT COALESCE(i.vendor_name, 'Unknown vendor') AS vendor,
                   COALESCE(SUM(i.total_amount), 0) AS total
            FROM invoices i JOIN documents d ON d.id = i.document_id
            WHERE """ + inv_where + " GROUP BY vendor ORDER BY total DESC", inv_params).fetchall()
        document_clauses, document_params = [], []
        if user_id is not None:
            document_clauses.append('d.user_id = ?')
            document_params.append(user_id)
        if filters['document_type']:
            document_clauses.append('d.document_type = ?')
            document_params.append(filters['document_type'])
        if filters['currency']:
            document_clauses.append('(t.currency = ? OR i.currency = ?)')
            document_params.extend([filters['currency'], filters['currency']])
        if filters['date_from']:
            document_clauses.append('(t.transaction_date >= ? OR i.invoice_date >= ?)')
            document_params.extend([filters['date_from'], filters['date_from']])
        if filters['date_to']:
            document_clauses.append('(t.transaction_date <= ? OR i.invoice_date <= ?)')
            document_params.extend([filters['date_to'], filters['date_to']])
        if filters['month']:
            document_clauses.append('(SUBSTR(t.transaction_date, 1, 7) = ? OR SUBSTR(i.invoice_date, 1, 7) = ?)')
            document_params.extend([filters['month'], filters['month']])
        if filters['year']:
            document_clauses.append('(SUBSTR(t.transaction_date, 1, 4) = ? OR SUBSTR(i.invoice_date, 1, 4) = ?)')
            document_params.extend([filters['year'], filters['year']])
        recent_where = ' AND '.join(document_clauses) or '1 = 1'
        recent_rows = conn.execute("""
            SELECT DISTINCT d.id, d.filename, d.document_type, d.upload_date,
                            d.processing_status, d.currency, d.bank_name,
                            d.account_holder, d.statement_start_date,
                            d.statement_end_date, d.opening_balance,
                            d.closing_balance, i.vendor_name,
                            i.total_amount AS invoice_total
            FROM documents d
            LEFT JOIN transactions t ON t.document_id = d.id
            LEFT JOIN invoices i ON i.document_id = d.id
            WHERE """ + recent_where + " ORDER BY d.created_at DESC, d.id DESC", document_params).fetchall()
        document_count_rows = conn.execute("""
            SELECT d.document_type, COUNT(DISTINCT d.id) AS document_count
            FROM documents d
            LEFT JOIN transactions t ON t.document_id = d.id
            LEFT JOIN invoices i ON i.document_id = d.id
            WHERE """ + recent_where + " GROUP BY d.document_type", document_params).fetchall()
        document_counts = {row['document_type']: int(row['document_count']) for row in document_count_rows}
        statement_rows = conn.execute("""
            SELECT DISTINCT d.id, d.filename, d.bank_name, d.account_holder,
                            d.statement_start_date, d.statement_end_date,
                            d.opening_balance, d.closing_balance, d.currency,
                            COUNT(t.id) OVER (PARTITION BY d.id) AS transaction_count
            FROM documents d
            LEFT JOIN transactions t ON t.document_id = d.id
            LEFT JOIN invoices i ON i.document_id = d.id
            WHERE d.document_type = 'bank_statement' AND """ + recent_where +
            " ORDER BY d.created_at DESC, d.id DESC", document_params).fetchall()

        missing_data_alert = detect_missing_periods(conn, filters, user_id=user_id)
        from services.risk_detector import detect_financial_anomalies
        risk_alerts = detect_financial_anomalies(conn, filters, user_id=user_id)
        from services.forecaster import generate_cash_flow_forecast
        forecast = generate_cash_flow_forecast(conn, filters, user_id=user_id)

        def nullable_float(value):
            return float(value) if value is not None else None

        return {
            'total_income': total_income,
            'total_expenses': total_expenses,
            'net_cash_flow': net_cash_flow,
            'transaction_count': int(tx_stats['transaction_count']),
            'credit_count': int(tx_stats['credit_count'] or 0),
            'debit_count': int(tx_stats['debit_count'] or 0),
            'income_transaction_count': int(tx_stats['credit_count'] or 0),
            'expense_transaction_count': int(tx_stats['debit_count'] or 0),
            'average_income': nullable_float(tx_stats['average_income']),
            'average_expense': nullable_float(tx_stats['average_expense']),
            'average_transaction': nullable_float(tx_stats['average_transaction']),
            'highest_income': nullable_float(tx_stats['highest_credit']),
            'highest_expense': nullable_float(tx_stats['highest_debit']),
            'highest_credit': nullable_float(tx_stats['highest_credit']),
            'highest_debit': nullable_float(tx_stats['highest_debit']),
            'total_invoiced': total_invoiced,
            'invoice_count': invoice_count,
            'average_invoice': nullable_float(inv_stats['average_invoice']),
            'highest_invoice': nullable_float(inv_stats['highest_invoice']),
            'total_tax': float(inv_stats['total_tax']),
            'total_discount': float(inv_stats['total_discount']),
            'paid_invoices': paid_invoices,
            'pending_invoices': invoice_count - paid_invoices,
            'matched_amount': float(inv_stats['matched_amount']),
            'unmatched_amount': total_invoiced - float(inv_stats['matched_amount']),
            'monthly_trends': monthly_trends,
            'categories': categories,
            'vendor_totals': [{'vendor': r['vendor'], 'total': float(r['total'])} for r in vendor_rows],
            'top_transactions': [dict(r) for r in transaction_rows],
            'top_expenses': [dict(r) for r in expense_rows],
            'recent_expenses': [dict(r) for r in recent_expense_rows],
            'recent_documents': [dict(r) for r in recent_rows],
            'document_counts': document_counts,
            'bank_statements': [dict(r) for r in statement_rows],
            'has_data': bool(tx_stats['transaction_count'] or invoice_count),
            'filters': filters,
            'missing_data_alert': missing_data_alert,
            'risk_alerts': risk_alerts,
            'forecast': forecast,
        }


def reconcile_invoices_and_transactions(db_path=DATABASE_PATH, user_id=None):
    """
    Automated Reconciliation:
    Matches unpaid invoices with bank statement debit transactions within the same user account.
    """
    with get_connection(db_path) as conn:
        if user_id is not None:
            invoices = conn.execute("""
                SELECT i.* FROM invoices i
                JOIN documents d ON d.id = i.document_id
                WHERE i.reconciliation_status = 'PENDING' AND d.user_id = ?
            """, (user_id,)).fetchall()
        else:
            invoices = conn.execute("SELECT * FROM invoices WHERE reconciliation_status = 'PENDING'").fetchall()
        reconciled_count = 0

        for inv in invoices:
            inv_total = inv['total_amount']
            vendor = (inv['vendor_name'] or '').lower().split()[0] if inv['vendor_name'] else ''

            # Find matching debit transaction belonging to same user
            if user_id is not None:
                tx = conn.execute("""
                    SELECT t.id, t.description, t.debit, t.transaction_date 
                    FROM transactions t
                    JOIN documents d ON d.id = t.document_id
                    WHERE t.debit = ? 
                      AND (? = '' OR LOWER(t.description) LIKE ?)
                      AND d.user_id = ?
                    LIMIT 1
                """, (inv_total, vendor, f"%{vendor}%", user_id)).fetchone()
            else:
                tx = conn.execute("""
                    SELECT id, description, debit, transaction_date 
                    FROM transactions 
                    WHERE debit = ? 
                      AND (? = '' OR LOWER(description) LIKE ?)
                    LIMIT 1
                """, (inv_total, vendor, f"%{vendor}%")).fetchone()

            if tx:
                conn.execute("""
                    UPDATE invoices 
                    SET reconciliation_status = 'PAID', reconciled_transaction_id = ?
                    WHERE id = ?
                """, (tx['id'], inv['id']))
                reconciled_count += 1

        if user_id is not None:
            all_invoices = conn.execute("""
                SELECT i.*, t.transaction_date AS paid_date, t.description AS paid_description
                FROM invoices i
                JOIN documents d ON d.id = i.document_id
                LEFT JOIN transactions t ON t.id = i.reconciled_transaction_id
                WHERE d.user_id = ?
                ORDER BY i.created_at DESC
            """, (user_id,)).fetchall()
        else:
            all_invoices = conn.execute("""
                SELECT i.*, t.transaction_date AS paid_date, t.description AS paid_description
                FROM invoices i
                LEFT JOIN transactions t ON t.id = i.reconciled_transaction_id
                ORDER BY i.created_at DESC
            """).fetchall()

        return [dict(r) for r in all_invoices]


def get_reconciled_invoices(db_path=DATABASE_PATH, filters=None, user_id=None):
    """Return reconciliation rows limited to the dashboard filter set."""
    values = _filter_values(filters)
    where, params = _invoice_where(values, user_id=user_id)
    with get_connection(db_path) as conn:
        rows = conn.execute("""
            SELECT i.*, t.transaction_date AS paid_date,
                   t.description AS paid_description
            FROM invoices i
            JOIN documents d ON d.id = i.document_id
            LEFT JOIN transactions t ON t.id = i.reconciled_transaction_id
            WHERE """ + where + " ORDER BY i.created_at DESC", params).fetchall()
        return [dict(row) for row in rows]


def get_analytics_filter_options(db_path=DATABASE_PATH, user_id=None):
    """Return stored currencies and available years for filter controls."""
    with get_connection(db_path) as conn:
        if user_id is not None:
            currencies = conn.execute("""
                SELECT t.currency AS currency FROM transactions t JOIN documents d ON d.id = t.document_id WHERE t.currency IS NOT NULL AND d.user_id = ?
                UNION SELECT i.currency AS currency FROM invoices i JOIN documents d ON d.id = i.document_id WHERE i.currency IS NOT NULL AND d.user_id = ?
                ORDER BY 1
            """, (user_id, user_id)).fetchall()
            years = conn.execute("""
                SELECT SUBSTR(t.transaction_date, 1, 4) AS year FROM transactions t JOIN documents d ON d.id = t.document_id
                WHERE t.transaction_date IS NOT NULL AND d.user_id = ?
                UNION SELECT SUBSTR(i.invoice_date, 1, 4) AS year FROM invoices i JOIN documents d ON d.id = i.document_id
                WHERE i.invoice_date IS NOT NULL AND d.user_id = ?
                ORDER BY 1 DESC
            """, (user_id, user_id)).fetchall()
        else:
            currencies = conn.execute("""
                SELECT currency FROM transactions WHERE currency IS NOT NULL
                UNION SELECT currency FROM invoices WHERE currency IS NOT NULL
                ORDER BY 1
            """).fetchall()
            years = conn.execute("""
                SELECT SUBSTR(transaction_date, 1, 4) AS year FROM transactions
                WHERE transaction_date IS NOT NULL
                UNION SELECT SUBSTR(invoice_date, 1, 4) AS year FROM invoices
                WHERE invoice_date IS NOT NULL
                ORDER BY 1 DESC
            """).fetchall()
        return {
            'currencies': [row[0] for row in currencies],
            'years': [row[0] for row in years],
        }
        return {
            'currencies': [row['currency'] for row in currencies],
            'years': [row['year'] for row in years],
        }
