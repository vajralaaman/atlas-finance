"""Automated financial anomaly, outlier, and duplicate fraud detection engine."""

from datetime import datetime


def detect_financial_anomalies(conn, filters=None, user_id=None):
    """
    Scan verified SQLite records for accounting risks scoped to user:
    1. Duplicate Invoice Number submissions (duplicate payment risk).
    2. High-Value Expense Outliers (debts > 2.5x the mean expense).
    3. Unreconciled Stale Invoices (pending payments > 45 days).
    """
    alerts = []
    user_param = (user_id, user_id)

    # 1. Duplicate Invoice Detection
    duplicate_rows = conn.execute("""
        SELECT i.invoice_number, i.vendor_name, COUNT(i.id) AS submission_count,
               SUM(i.total_amount) AS combined_total
        FROM invoices i
        JOIN documents d ON d.id = i.document_id
        WHERE i.invoice_number IS NOT NULL AND TRIM(i.invoice_number) != ''
          AND (d.user_id = ? OR ? IS NULL)
        GROUP BY LOWER(TRIM(i.invoice_number))
        HAVING COUNT(i.id) > 1
    """, user_param).fetchall()

    for dup in duplicate_rows:
        inv_num = dup['invoice_number']
        vendor = dup['vendor_name'] or 'Unknown Vendor'
        count = dup['submission_count']
        alerts.append({
            'type': 'duplicate_invoice',
            'severity': 'danger',
            'icon': '🚨',
            'title': f'Duplicate Invoice Risk: #{inv_num}',
            'description': f'Invoice #{inv_num} from {vendor} was uploaded {count} times. Review to prevent double-payment liability.',
            'count': count
        })

    # 2. Expense Outlier Spike Detection
    stats_row = conn.execute("""
        SELECT AVG(t.debit) AS avg_debit, MAX(t.debit) AS max_debit,
               COUNT(t.id) AS debit_count
        FROM transactions t
        JOIN documents d ON d.id = t.document_id
        WHERE t.debit > 0 AND (d.user_id = ? OR ? IS NULL)
    """, user_param).fetchone()

    avg_debit = float(stats_row['avg_debit'] or 0)
    debit_count = int(stats_row['debit_count'] or 0)

    if debit_count >= 3 and avg_debit > 0:
        threshold = avg_debit * 2.5
        outlier_rows = conn.execute("""
            SELECT t.transaction_date, t.description, t.debit, t.currency
            FROM transactions t
            JOIN documents d ON d.id = t.document_id
            WHERE t.debit >= ? AND (d.user_id = ? OR ? IS NULL)
            ORDER BY t.debit DESC
            LIMIT 3
        """, (threshold, user_id, user_id)).fetchall()

        for out in outlier_rows:
            amt = float(out['debit'])
            desc = out['description']
            dt = out['transaction_date'] or 'Date unavailable'
            alerts.append({
                'type': 'expense_outlier',
                'severity': 'warning',
                'icon': '⚡',
                'title': f'Unusual Expense Spike: ₹{amt:,.2f}',
                'description': f'Transaction "{desc}" on {dt} exceeds 2.5× the average expense (₹{avg_debit:,.2f}). Requires audit verification.',
                'amount': amt
            })

    # 3. Unreconciled Stale Invoices (> 45 days old)
    today = datetime.now()
    pending_rows = conn.execute("""
        SELECT i.invoice_number, i.vendor_name, i.invoice_date, i.total_amount
        FROM invoices i
        JOIN documents d ON d.id = i.document_id
        WHERE i.reconciliation_status = 'PENDING' AND i.invoice_date IS NOT NULL
          AND (d.user_id = ? OR ? IS NULL)
        ORDER BY i.invoice_date ASC
    """, user_param).fetchall()

    stale_count = 0
    for row in pending_rows:
        try:
            inv_dt = datetime.strptime(row['invoice_date'], '%Y-%m-%d')
            age_days = (today - inv_dt).days
            if age_days > 45:
                stale_count += 1
        except Exception:
            continue

    if stale_count > 0:
        alerts.append({
            'type': 'stale_invoice',
            'severity': 'info',
            'icon': '⏳',
            'title': f'{stale_count} Overdue Unreconciled Invoice(s)',
            'description': f'{stale_count} supplier bills have remained unpaid for over 45 days. Review cash flow to avoid late fees.',
            'count': stale_count
        })

    return alerts
