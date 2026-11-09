"""Predictive Cash Flow and Financial Runway Forecasting Engine."""

import sys
import statistics
from datetime import datetime
from pathlib import Path

# Ensure project root is in sys.path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from config import DATABASE_PATH
from database.db import get_connection
from services.analytics import _filter_values, _transaction_where


def _next_month_str(ym_str, offset=1):
    """Compute 'YYYY-MM' offset by specified months."""
    try:
        year, month = map(int, ym_str.split('-'))
    except Exception:
        today = datetime.now()
        year, month = today.year, today.month

    total_months = month - 1 + offset
    new_year = year + (total_months // 12)
    new_month = (total_months % 12) + 1
    return f"{new_year:04d}-{new_month:02d}"


def _format_month_display(ym_str):
    """Convert '2026-09' to 'September 2026'."""
    try:
        dt = datetime.strptime(ym_str, '%Y-%m')
        return dt.strftime('%B %Y')
    except Exception:
        return ym_str


def generate_cash_flow_forecast(conn, filters=None, user_id=None):
    """
    Generate predictive 30-day and 60-day cash flow projections and runway analysis.
    Uses linear regression on historical monthly trend data and burn rate modeling.
    """
    filters = _filter_values(filters)
    tx_where, tx_params = _transaction_where(filters, user_id=user_id)

    # 1. Fetch chronological monthly historical figures
    rows = conn.execute("""
        SELECT SUBSTR(t.transaction_date, 1, 7) AS month,
               COALESCE(SUM(t.credit), 0) AS income,
               COALESCE(SUM(t.debit), 0) AS expenses
        FROM transactions t
        JOIN documents d ON d.id = t.document_id
        WHERE t.transaction_date IS NOT NULL AND """ + tx_where + """
        GROUP BY month
        ORDER BY month ASC
    """, tx_params).fetchall()

    if not rows:
        return {
            'has_forecast': False,
            'message': 'Upload bank statements to generate predictive cash flow forecasts.'
        }

    monthly_data = [{'month': r['month'], 'income': float(r['income']), 'expenses': float(r['expenses'])} for r in rows]
    n = len(monthly_data)
    latest_month = monthly_data[-1]['month']

    # 2. Next month labels
    next_m1_str = _next_month_str(latest_month, 1)
    next_m2_str = _next_month_str(latest_month, 2)
    next_m1_label = _format_month_display(next_m1_str)
    next_m2_label = _format_month_display(next_m2_str)

    # 3. Forecast calculation
    if n >= 2:
        x = list(range(1, n + 1))
        y_inc = [m['income'] for m in monthly_data]
        y_exp = [m['expenses'] for m in monthly_data]

        try:
            slope_inc, intercept_inc = statistics.linear_regression(x, y_inc)
            proj_income_30d = max(0.0, slope_inc * (n + 1) + intercept_inc)
            proj_income_60d = max(0.0, slope_inc * (n + 2) + intercept_inc)
        except Exception:
            proj_income_30d = sum(y_inc) / n
            proj_income_60d = proj_income_30d

        try:
            slope_exp, intercept_exp = statistics.linear_regression(x, y_exp)
            proj_expense_30d = max(0.0, slope_exp * (n + 1) + intercept_exp)
            proj_expense_60d = max(0.0, slope_exp * (n + 2) + intercept_exp)
        except Exception:
            proj_expense_30d = sum(y_exp) / n
            proj_expense_60d = proj_expense_30d

        avg_monthly_burn = sum(y_exp) / n
        confidence = 'High (Statistical linear regression on multi-month trends)'
    else:
        # Single-month baseline extrapolation
        current_inc = monthly_data[0]['income']
        current_exp = monthly_data[0]['expenses']
        proj_income_30d = current_inc
        proj_income_60d = current_inc * 1.02  # modest baseline growth projection
        proj_expense_30d = current_exp
        proj_expense_60d = current_exp * 1.01
        avg_monthly_burn = current_exp
        confidence = 'Moderate (Extrapolated from single-period transaction run-rate)'

    # 4. Net Cash Flow Projections
    proj_net_30d = proj_income_30d - proj_expense_30d
    proj_net_60d = proj_income_60d - proj_expense_60d

    # 5. Financial Liquidity Runway Analysis
    total_income_all = sum(m['income'] for m in monthly_data)
    total_expense_all = sum(m['expenses'] for m in monthly_data)
    current_cash_reserve = max(0.0, total_income_all - total_expense_all)

    if avg_monthly_burn > 0:
        runway_months = round(current_cash_reserve / avg_monthly_burn, 1)
    else:
        runway_months = 12.0  # Zero burn indicates sustainable cash reserve

    if runway_months >= 6.0:
        runway_status = 'Healthy Runway'
        runway_badge_class = 'success'
        runway_note = 'Strong liquidity buffer exceeding 6 months of operational burn.'
    elif runway_months >= 3.0:
        runway_status = 'Moderate Runway'
        runway_badge_class = 'warning'
        runway_note = 'Sufficient liquidity for 3 to 6 months. Monitor upcoming supplier payables.'
    else:
        runway_status = 'Low Runway'
        runway_badge_class = 'danger'
        runway_note = 'Less than 3 months of operational liquidity buffer. Accelerate receivables.'

    # Trend Direction
    if proj_net_30d >= 0:
        trend_direction = 'Positive (Projected monthly operating surplus)'
    else:
        trend_direction = 'Deficit (Projected monthly net cash outflow)'

    return {
        'has_forecast': True,
        'next_month_label': next_m1_label,
        'second_month_label': next_m2_label,
        'projected_income_30d': round(proj_income_30d, 2),
        'projected_expense_30d': round(proj_expense_30d, 2),
        'projected_net_30d': round(proj_net_30d, 2),
        'projected_income_60d': round(proj_income_60d, 2),
        'projected_expense_60d': round(proj_expense_60d, 2),
        'projected_net_60d': round(proj_net_60d, 2),
        'monthly_burn_rate': round(avg_monthly_burn, 2),
        'cash_reserve': round(current_cash_reserve, 2),
        'runway_months': runway_months,
        'runway_status': runway_status,
        'runway_badge_class': runway_badge_class,
        'runway_note': runway_note,
        'trend_direction': trend_direction,
        'confidence': confidence,
    }
