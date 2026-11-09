"""Information extraction for bank statements and invoices."""

import sys
import re
from pathlib import Path

# Ensure project root is in sys.path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from services.standardizer import (
    mask_account_number, normalize_date, normalize_numeric,
    normalize_currency, categorize_transaction,
)

DATE_REGEX = r'\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2}|\d{1,2} (?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{4})\b'
AMOUNT_REGEX = r'[-+]?[$€£¥₹]?\d[\d,]*(?:\.\d{1,2})?'


def _numbers(value):
    return [normalize_numeric(item) for item in re.findall(AMOUNT_REGEX, value or '')]


def _value_after_label(lines, index, label_pattern):
    match = re.search(label_pattern, lines[index], re.IGNORECASE)
    if not match:
        return None
    remainder = lines[index][match.end():].strip(' :|-')
    if remainder:
        return remainder.split('|')[0].strip()
    for following in lines[index + 1:index + 3]:
        if following.strip():
            return following.strip().split('|')[0].strip()
    return None


def _amount_after_label(lines, index, label_pattern):
    value = _value_after_label(lines, index, label_pattern)
    values = _numbers(value or '')
    return values[-1] if values else None


def _parse_transaction_line(line, date_match):
    remainder = line[date_match.end():].strip(' |')
    numbers = _numbers(remainder)
    lower = remainder.lower()
    debit = None
    credit = None
    if re.search(r'\b(?:debit|dr|withdrawal)\b', lower):
        debit = numbers[0] if numbers else None
    elif re.search(r'\b(?:credit|cr|deposit|salary|income)\b', lower):
        credit = numbers[0] if numbers else None
    balance = numbers[-1] if len(numbers) >= 2 else None
    description = re.sub(AMOUNT_REGEX, '', remainder)
    description = re.sub(r'\b(?:debit|credit|dr|cr|withdrawal|deposit)\b', '', description, flags=re.IGNORECASE)
    description = re.sub(r'\bBalance\b', '', description, flags=re.IGNORECASE).strip(' -:|')
    return {
        'date': normalize_date(date_match.group(0)),
        'description': description or 'Transaction',
        'debit': debit,
        'credit': credit,
        'balance': balance,
        'category': categorize_transaction(description),
    }


def _parse_columnar_transaction(lines, index, date_match):
    fields = []
    for value in lines[index + 1:]:
        if re.fullmatch(DATE_REGEX, value.strip(), re.IGNORECASE):
            break
        if value.strip():
            fields.append(value.strip())
        if len(fields) == 4:
            break
    if len(fields) < 4:
        return None
    debit = _numbers(fields[1])
    credit = _numbers(fields[2])
    balance = _numbers(fields[3])
    description = fields[0]
    return {
        'date': normalize_date(date_match.group(0)),
        'description': description,
        'debit': debit[-1] if debit and fields[1] != '-' else None,
        'credit': credit[-1] if credit and fields[2] != '-' else None,
        'balance': balance[-1] if balance else None,
        'category': categorize_transaction(description),
    }


def parse_bank_statement(text):
    """Extract metadata and transactions from common row or column PDF layouts."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    bank_name = next((line for line in lines if 'bank' in line.lower() and 'statement' not in line.lower()), None)
    if not bank_name:
        bank_name = next((line for line in lines if 'bank' in line.lower()), None)

    account_holder = None
    account_number = None
    currency = 'INR'
    for index, line in enumerate(lines):
        if re.search(r'account holder|customer name|name\s*:', line, re.IGNORECASE):
            account_holder = _value_after_label(lines, index, r'(?:account holder|customer name|name\s*:)' )
        if re.search(r'account number|account no|a/c no', line, re.IGNORECASE):
            account_number = _value_after_label(lines, index, r'(?:account number|account no|a/c no)')
        if re.search(r'currency\s*:', line, re.IGNORECASE):
            currency = normalize_currency(_value_after_label(lines, index, r'currency\s*:'))

    dates = re.findall(DATE_REGEX, text, re.IGNORECASE)
    period_match = re.search(r'(?:statement period|period)\s*:\s*(' + DATE_REGEX + r')\s+(?:to|-)\s+(' + DATE_REGEX + r')', text, re.IGNORECASE)
    start_date = normalize_date(period_match.group(1)) if period_match else normalize_date(dates[0]) if dates else None
    end_date = normalize_date(period_match.group(2)) if period_match else normalize_date(dates[-1]) if len(dates) > 1 else start_date

    opening_balance = None
    closing_balance = None
    for index, line in enumerate(lines):
        if re.match(r'opening balance\s*:', line, re.IGNORECASE):
            opening_balance = _amount_after_label(lines, index, r'opening balance\s*:')
        if re.match(r'closing balance\s*:', line, re.IGNORECASE):
            closing_balance = _amount_after_label(lines, index, r'closing balance\s*:')

    transactions = []
    for index, line in enumerate(lines):
        date_match = re.search(DATE_REGEX, line, re.IGNORECASE)
        if not date_match:
            continue
        if re.fullmatch(DATE_REGEX, line, re.IGNORECASE):
            transaction = _parse_columnar_transaction(lines, index, date_match)
        else:
            transaction = _parse_transaction_line(line, date_match)
        if transaction and transaction['date'] and (transaction['debit'] is not None or transaction['credit'] is not None):
            transactions.append(transaction)

    if opening_balance is None and transactions:
        opening_balance = transactions[0]['balance'] - (transactions[0]['credit'] or 0) + (transactions[0]['debit'] or 0)
    if closing_balance is None and transactions:
        closing_balance = transactions[-1]['balance']

    return {
        'statement_information': {
            'bank_name': bank_name or 'Bank',
            'account_holder': account_holder or 'Valued Customer',
            'account_number': mask_account_number(account_number),
            'statement_start_date': start_date,
            'statement_end_date': end_date,
            'opening_balance': opening_balance,
            'closing_balance': closing_balance,
            'currency': currency,
        },
        'transactions': transactions,
    }


def _first_meaningful_vendor(lines):
    for line in lines[1:]:
        lower = line.lower()
        if line and not any(term in lower for term in ('address', 'invoice', 'sample', 'tax', 'currency', 'number:')):
            return line
    return None


def _line_after_label(lines, label_pattern):
    for index, line in enumerate(lines):
        if re.search(label_pattern, line, re.IGNORECASE):
            value = _value_after_label(lines, index, label_pattern)
            if value:
                return value
    return None


def _parse_invoice_items(lines):
    items = []
    start = next((index for index, line in enumerate(lines) if 'line total' in line.lower()), None)
    if start is None:
        return items
    fields = []
    for line in lines[start + 1:]:
        if re.match(r'(?:subtotal|tax|gst|discount|total due|total amount)', line, re.IGNORECASE):
            break
        fields.append(line)
    for index in range(0, len(fields) - 3, 4):
        description, quantity, unit_price, line_total = fields[index:index + 4]
        numbers = [_numbers(value) for value in (quantity, unit_price, line_total)]
        if all(values for values in numbers):
            items.append({
                'product_or_service': description,
                'quantity': numbers[0][-1],
                'unit_price': numbers[1][-1],
                'line_total': numbers[2][-1],
            })
    return items


def parse_invoice(text):
    """Extract invoice metadata from labeled and multi-line invoice layouts."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    invoice_number = _line_after_label(lines, r'invoice\s+(?:number|no\.?)[\s:]*')
    invoice_date = _line_after_label(lines, r'invoice\s+date\s*:\s*')
    due_date = _line_after_label(lines, r'due\s+date\s*:\s*')
    vendor = _line_after_label(lines, r'(?:from|vendor|supplier)\s*:\s*') or _first_meaningful_vendor(lines)
    customer = _line_after_label(lines, r'(?:bill\s+to|customer|to)\s*:\s*')
    currency = _line_after_label(lines, r'currency\s*:\s*') or 'INR'

    invoice_date = normalize_date(invoice_date)
    due_date = normalize_date(due_date)
    total_amount = None
    subtotal = None
    tax = None
    discount = None
    for index, line in enumerate(lines):
        if re.match(r'(?:total due|total amount|grand total)\b', line, re.IGNORECASE):
            total_amount = _amount_after_label(lines, index, r'(?:total due|total amount|grand total)')
        elif re.match(r'subtotal\b', line, re.IGNORECASE):
            subtotal = _amount_after_label(lines, index, r'subtotal')
        elif re.match(r'(?:gst|tax)\b', line, re.IGNORECASE):
            tax = _amount_after_label(lines, index, r'(?:gst|tax)')
        elif re.match(r'discount\b', line, re.IGNORECASE):
            discount = _amount_after_label(lines, index, r'discount')

    return {
        'invoice_number': invoice_number or 'INV-001',
        'invoice_date': invoice_date,
        'due_date': due_date,
        'vendor_name': vendor or 'Vendor',
        'customer_name': customer or 'Customer',
        'currency': normalize_currency(currency),
        'subtotal': subtotal if subtotal is not None else total_amount,
        'tax': tax if tax is not None else 0.0,
        'discount': discount if discount is not None else 0.0,
        'total_amount': total_amount if total_amount is not None else 0.0,
        'items': _parse_invoice_items(lines),
    }
