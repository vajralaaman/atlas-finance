"""PyMuPDF Text Extractor with At-Rest Decryption Support."""

import sys
from pathlib import Path

# Ensure project root is in sys.path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import fitz  # PyMuPDF
from services.crypto import decrypt_file_to_bytes, is_encrypted_bytes, decrypt_bytes


def extract_text_from_pdf(pdf_source):
    """Extract clean page-by-page text from a PDF path or raw/encrypted bytes."""
    try:
        if isinstance(pdf_source, (bytes, bytearray)):
            raw_bytes = decrypt_bytes(pdf_source) if is_encrypted_bytes(pdf_source) else bytes(pdf_source)
            doc = fitz.open(stream=raw_bytes, filetype="pdf")
        else:
            path = Path(pdf_source)
            if not path.exists():
                return {'success': False, 'text': '', 'page_count': 0, 'error': f'File not found: {path}'}
            decrypted_bytes = decrypt_file_to_bytes(path)
            doc = fitz.open(stream=decrypted_bytes, filetype="pdf")

        if doc.page_count == 0:
            return {'success': False, 'text': '', 'page_count': 0, 'error': 'PDF file is empty.'}

        pages_text = []
        for i in range(doc.page_count):
            page = doc[i]
            text = page.get_text()
            clean_lines = [line.rstrip() for line in text.splitlines() if line.strip()]
            pages_text.append('\n'.join(clean_lines))

        doc.close()
        full_text = '\n\n'.join(pages_text).strip()

        if not full_text:
            return {
                'success': False,
                'text': '',
                'page_count': len(pages_text),
                'error': 'No extractable text found (document might be a scanned image).'
            }

        return {'success': True, 'text': full_text, 'page_count': len(pages_text), 'error': None}
    except Exception as e:
        return {'success': False, 'text': '', 'page_count': 0, 'error': f'Error reading PDF: {str(e)}'}
