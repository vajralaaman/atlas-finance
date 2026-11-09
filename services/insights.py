"""Database-grounded financial questions and lightweight dashboard insights."""

import json
import os
import re
import sys
from pathlib import Path
from calendar import month_name
from urllib.error import URLError
from urllib.request import Request, urlopen

# Ensure project root is in sys.path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from config import DATABASE_PATH
from database.db import get_connection
from services.analytics import get_financial_overview


_MONTHS = {name.lower(): number for number, name in enumerate(month_name) if name}
_MONTHS.update({name[:3].lower(): number for number, name in enumerate(month_name) if name})


def _money(value, currency=''):
    if value is None:
        return 'Data not available'
    prefix = f'{currency} ' if currency else ''
    return f'{prefix}{float(value):,.2f}'


def _month_value(question):
    words = re.findall(r'[a-z]+', question.lower())
    for word in words:
        if word in _MONTHS:
            return f'{_MONTHS[word]:02d}'
    return None


def _year_value(question):
    match = re.search(r'\b(20\d{2})\b', question)
    return match.group(1) if match else None


def _question_result(question, db_path, filters=None, user_id=None):
    question_lower = question.lower()
    overview = get_financial_overview(db_path, filters, user_id=user_id)
    if not overview['has_data']:
        return None

    currency = filters.get('currency', '') if filters else ''
    if 'unmatched' in question_lower and ('invoice' in question_lower or 'invoices' in question_lower):
        return {
            'answer': f"{overview['pending_invoices']} unmatched invoice(s).",
            'value': overview['pending_invoices'],
            'unit': 'invoices',
        }
    if 'vendor' in question_lower and ('highest' in question_lower or 'most' in question_lower) and 'invoice' in question_lower:
        vendors = overview['vendor_totals']
        if not vendors:
            return None
        vendor = vendors[0]
        return {
            'answer': f"{vendor['vendor']} has the highest invoice amount at {_money(vendor['total'], currency)}.",
            'value': vendor['total'],
            'unit': 'currency',
        }
    if 'compare' in question_lower and 'expense' in question_lower:
        month_matches = re.findall(r'\b(' + '|'.join(_MONTHS) + r')\b', question_lower)
        if len(month_matches) >= 2:
            trends = overview['monthly_trends']
            values = {}
            for trend in trends:
                month_number = trend['month'][5:7]
                for month in month_matches[:2]:
                    if month_number == f'{_MONTHS[month]:02d}' and (not _year_value(question) or trend['month'].startswith(_year_value(question))):
                        values[month.title()] = trend['expenses']
            if len(values) == 2:
                first, second = values.items()
                difference = second[1] - first[1]
                direction = 'increased' if difference > 0 else 'decreased' if difference < 0 else 'did not change'
                return {
                    'answer': f"Expenses {direction} by {_money(abs(difference), currency)} from {first[0]} ({_money(first[1], currency)}) to {second[0]} ({_money(second[1], currency)}).",
                    'value': difference,
                    'unit': 'currency',
                }
        return None
    month = _month_value(question)
    if month and ('spend' in question_lower or 'expense' in question_lower):
        default_year = (overview['monthly_trends'][0]['month'][:4]
                        if overview['monthly_trends'] else None)
        if not default_year and not _year_value(question):
            return None
        month_filters = dict(filters or {})
        month_filters['month'] = f"{_year_value(question) or default_year}-{month}"
        monthly = get_financial_overview(db_path, month_filters, user_id=user_id)
        if not monthly['has_data']:
            return None
        return {
            'answer': f"You spent {_money(monthly['total_expenses'], currency)} in {month_name[int(month)]}.",
            'value': monthly['total_expenses'],
            'unit': 'currency',
        }
    if 'total income' in question_lower or ('income' in question_lower and 'how much' in question_lower):
        return {'answer': f"Your total income is {_money(overview['total_income'], currency)}.", 'value': overview['total_income'], 'unit': 'currency'}
    if 'highest expense' in question_lower or 'largest expense' in question_lower:
        expense = overview['top_expenses'][0] if overview['top_expenses'] else None
        if not expense:
            return None
        return {
            'answer': f"Your highest expense was {_money(expense['amount'], currency)} for {expense['description'] or 'an undescribed transaction'}.",
            'value': expense['amount'],
            'unit': 'currency',
        }
    if 'runway' in question_lower or 'burn' in question_lower or 'survive' in question_lower:
        fc = overview.get('forecast', {})
        if fc and fc.get('has_forecast'):
            return {
                'answer': f"Current cash runway is estimated at {fc['runway_months']} months ({fc['runway_status']}) with an average monthly burn rate of {_money(fc['monthly_burn_rate'], currency)}.",
                'value': fc['runway_months'],
                'unit': 'months',
            }
    if 'forecast' in question_lower or 'project' in question_lower or 'future' in question_lower:
        fc = overview.get('forecast', {})
        if fc and fc.get('has_forecast'):
            net_sign = '+' if fc['projected_net_30d'] >= 0 else ''
            return {
                'answer': f"For {fc['next_month_label']}, projected income is {_money(fc['projected_income_30d'], currency)} against projected expenses of {_money(fc['projected_expense_30d'], currency)}, yielding a net cash flow of {net_sign}{_money(fc['projected_net_30d'], currency)}.",
                'value': fc['projected_net_30d'],
                'unit': 'currency',
            }
    return None


def _ai_explanation(question, result):
    endpoint = os.environ.get('FINANCIAL_AI_API_URL')
    api_key = os.environ.get('FINANCIAL_AI_API_KEY')
    if not endpoint or not api_key:
        return result['answer']
    prompt = (
        'Explain this verified financial answer in one concise sentence. '
        f'Question: {question[:300]} Verified answer: {result["answer"]}'
    )
    payload = json.dumps({'model': os.environ.get('FINANCIAL_AI_MODEL', 'financial-assistant'), 'messages': [
        {'role': 'user', 'content': prompt},
    ]}).encode('utf-8')
    request = Request(endpoint, data=payload, headers={
        'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json',
    }, method='POST')
    try:
        with urlopen(request, timeout=5) as response:
            body = json.loads(response.read().decode('utf-8'))
        explanation = body.get('choices', [{}])[0].get('message', {}).get('content', '').strip()
        return explanation or result['answer']
    except (OSError, URLError, ValueError, KeyError, IndexError):
        return result['answer']


def answer_financial_question(question, db_path=DATABASE_PATH, filters=None, user_id=None):
    """Answer supported questions from SQLite, optionally rephrased by an AI service."""
    question = (question or '').strip()
    if not question:
        return {'supported': False, 'answer': 'Please enter a financial question.'}
    result = _question_result(question, db_path, filters or {}, user_id=user_id)
    if result is None:
        return {'supported': False, 'answer': 'Data not available.'}
    return {'supported': True, 'answer': _ai_explanation(question, result), 'verified_answer': result['answer'], 'value': result['value'], 'unit': result['unit']}


def get_financial_insights(db_path=DATABASE_PATH, filters=None, user_id=None):
    """Build concise observations from verified dashboard aggregates."""
    overview = get_financial_overview(db_path, filters, user_id=user_id)
    if not overview['has_data']:
        return []
    insights = []
    trends = overview['monthly_trends']
    if len(trends) >= 2:
        previous, current = trends[-2], trends[-1]
        change = current['expenses'] - previous['expenses']
        direction = 'increased' if change > 0 else 'decreased' if change < 0 else 'did not change'
        insights.append(f"Expenses {direction} by {_money(abs(change))} from {previous['month']} to {current['month']}.")
    if overview['top_expenses']:
        expense = overview['top_expenses'][0]
        insights.append(f"Highest expense: {expense['description'] or 'Undescribed transaction'} at {_money(expense['amount'])}.")
    if overview['highest_income'] is not None:
        insights.append(f"Highest income transaction: {_money(overview['highest_income'])}.")
    if overview['net_cash_flow'] != 0:
        direction = 'positive' if overview['net_cash_flow'] > 0 else 'negative'
        insights.append(f"Net cash flow is {direction} at {_money(overview['net_cash_flow'])}.")
    if overview['invoice_count']:
        insights.append(f"{overview['pending_invoices']} invoice(s) remain unmatched.")
    return insights[:5]
