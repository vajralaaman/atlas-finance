"""Data normalization, PII masking, and categorization service."""

import math
import re
from datetime import datetime


def mask_account_number(acc):
    """Mask account numbers to preserve privacy (e.g., XXXX-XXXX-4567)."""
    if not acc:
        return None
    cleaned = re.sub(r'[\s-]', '', str(acc))
    if len(cleaned) <= 4:
        return 'XXXX-' + cleaned
    return 'XXXX-XXXX-' + cleaned[-4:]


def normalize_date(value):
    """Normalize various date formats into standard ISO-8601 (YYYY-MM-DD)."""
    if not value:
        return None
    val_str = str(value).strip()
    patterns = [
        '%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y', '%m/%d/%Y',
        '%d %b %Y', '%d-%b-%Y', '%d %B %Y', '%b %d, %Y'
    ]
    for fmt in patterns:
        try:
            return datetime.strptime(val_str, fmt).strftime('%Y-%m-%d')
        except ValueError:
            continue
    return None


def normalize_numeric(value):
    """Convert currency strings or numbers into clean floats."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if math.isfinite(value) else None

    cleaned = re.sub(r'[^\d.-]', '', str(value).replace(',', ''))
    try:
        num = float(cleaned)
        return round(num, 2) if math.isfinite(num) else None
    except ValueError:
        return None


def normalize_currency(curr):
    """Map common currency symbols and codes to ISO currency codes."""
    if not curr:
        return 'INR'
    curr_upper = str(curr).upper()
    if '₹' in curr or 'INR' in curr_upper:
        return 'INR'
    if '$' in curr or 'USD' in curr_upper:
        return 'USD'
    if '€' in curr or 'EUR' in curr_upper:
        return 'EUR'
    if '£' in curr or 'GBP' in curr_upper:
        return 'GBP'
    return curr_upper[:3]


def categorize_transaction(desc):
    """Rule-based categorization for financial intelligence."""
    if not desc:
        return 'General Expense'
    lower = desc.lower()

    if any(k in lower for k in ['salary', 'dividend', 'interest', 'deposit', 'payroll']):
        return 'Income & Salary'
    if any(k in lower for k in ['swiggy', 'zomato', 'restaurant', 'cafe', 'food', 'dining']):
        return 'Food & Dining'
    if any(k in lower for k in ['amazon', 'flipkart', 'store', 'retail', 'mart', 'supermarket']):
        return 'Shopping'
    if any(k in lower for k in ['electric', 'water', 'internet', 'airtel', 'jio', 'recharge', 'utility', 'bill']):
        return 'Utilities'
    if any(k in lower for k in ['hardware', 'packaging', 'supplier', 'vendor', 'materials', 'supplies']):
        return 'Supplies & Materials'
    if any(k in lower for k in ['rent', 'office', 'maintenance', 'space']):
        return 'Rent & Facilities'
    if any(k in lower for k in ['tax', 'gst', 'fee', 'charge', 'duty']):
        return 'Taxes & Fees'
    if any(k in lower for k in ['transfer', 'upi', 'atm', 'cash', 'withdrawal']):
        return 'Transfer / Cash'
    return 'General Expense'