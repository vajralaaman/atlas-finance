"""Document classification service."""

import os
import json
import urllib.request

BANK_KEYWORDS = [
    'statement', 'debit', 'credit', 'withdrawal', 'deposit',
    'opening balance', 'closing balance', 'account number', 'bank'
]

INVOICE_KEYWORDS = [
    'invoice', 'bill to', 'ship to', 'tax invoice', 'subtotal',
    'total amount', 'due date', 'unit price', 'line total', 'vendor'
]


def classify_document(text):
    """Classify text as 'bank_statement', 'invoice', or 'unknown'."""
    if not text or not text.strip():
        return {'document_type': 'unknown', 'method': 'rule_based'}

    # Optional AI call if API key configured
    api_key = os.getenv('AI_API_KEY') or os.getenv('OPENAI_API_KEY')
    base_url = os.getenv('AI_API_BASE_URL')
    if api_key and base_url:
        try:
            payload = {
                'model': os.getenv('AI_MODEL_NAME', 'gpt-4o-mini'),
                'messages': [
                    {'role': 'system', 'content': 'Classify document text. Return JSON: {"document_type": "bank_statement"|"invoice"|"unknown"}'},
                    {'role': 'user', 'content': text[:3000]}
                ],
                'temperature': 0
            }
            req = urllib.request.Request(
                base_url,
                data=json.dumps(payload).encode('utf-8'),
                headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {api_key}'},
                method='POST'
            )
            with urllib.request.urlopen(req, timeout=5) as res:
                body = json.loads(res.read().decode('utf-8'))
                res_content = json.loads(body['choices'][0]['message']['content'])
                if res_content.get('document_type') in {'bank_statement', 'invoice', 'unknown'}:
                    return {'document_type': res_content['document_type'], 'method': 'ai'}
        except Exception:
            pass  # Fall back to rule-based immediately

    # Deterministic keyword scoring
    lower = text.lower()
    bank_score = sum(1 for k in BANK_KEYWORDS if k in lower)
    invoice_score = sum(1 for k in INVOICE_KEYWORDS if k in lower)

    if bank_score > invoice_score and bank_score >= 2:
        return {'document_type': 'bank_statement', 'method': 'rule_based'}
    if invoice_score >= bank_score and invoice_score >= 2:
        return {'document_type': 'invoice', 'method': 'rule_based'}

    return {'document_type': 'unknown', 'method': 'rule_based'}