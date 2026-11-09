import io
from pathlib import Path

import fitz

from app import app

pdf_dir = Path('uploads')
pdf_dir.mkdir(exist_ok=True)
path = pdf_dir / 'sample_bank.pdf'

doc = fitz.open()
page = doc.new_page()
page.insert_text(
    (72, 72),
    'Bank Statement\nAccount Holder: John Smith\nAccount Number: 1234567890\nStatement Period: 01/01/2024 to 31/01/2024\nTransaction: Debit 100.00\nBalance: 2500.00'
)
doc.save(path)
doc.close()

client = app.test_client()
with open(path, 'rb') as f:
    pdf_bytes = f.read()

resp = client.post(
    '/upload',
    data={'files': (io.BytesIO(pdf_bytes), path.name, 'application/pdf')},
    content_type='multipart/form-data',
)
print('UPLOAD_STATUS', resp.status_code)
print('UPLOAD_JSON', resp.get_json())

with client.session_transaction() as sess:
    print('SESSION_HAS_DOCUMENTS', bool(sess.get('processed_documents')))

results = client.get('/results')
print('RESULTS_STATUS', results.status_code)
html = results.get_data(as_text=True)
print('HAS_BANK', 'Bank Statement' in html)
print('HAS_RAW_TEXT', 'Account Holder' in html)
print('HAS_STRUCTURED', 'Structured Information' in html)
