"""Unit tests for At-Rest Document Encryption (AES-256) and Decrypted Streaming."""

import io
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import fitz
from database.db import get_connection, init_db, save_document
from services.crypto import (
    get_encryption_key, encrypt_bytes, decrypt_bytes,
    save_encrypted_file, decrypt_file_to_bytes, is_encrypted_bytes
)
from services.extractor import extract_text_from_pdf
from app import app


class DocumentEncryptionTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.temp_path = Path(self.temp_dir.name)
        self.db_path = self.temp_path / 'test_crypto.db'
        init_db(self.db_path)

        app.config['TESTING'] = True
        app.config['UPLOAD_FOLDER'] = str(self.temp_path / 'uploads')
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        self.client = app.test_client()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_byte_encryption_roundtrip(self):
        """Plaintext bytes encrypt to Fernet tokens and decrypt back losslessly."""
        secret_content = b"%PDF-1.7 Confidential Bank Statement for Atlas Finance Inc."
        ciphertext = encrypt_bytes(secret_content)

        # Ciphertext must not contain plaintext
        self.assertNotIn(b"Confidential", ciphertext)
        self.assertTrue(is_encrypted_bytes(ciphertext))

        # Decrypt returns original content
        plaintext = decrypt_bytes(ciphertext)
        self.assertEqual(plaintext, secret_content)

    def test_at_rest_file_encryption(self):
        """Encrypted file on disk contains scrambled ciphertext, not raw PDF data."""
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((50, 50), "State Bank of India Private Ledger Balance INR 500,000")
        pdf_bytes = doc.write()
        doc.close()

        enc_path = self.temp_path / 'uploads' / 'secure_statement.pdf'
        save_encrypted_file(pdf_bytes, enc_path)

        # Verify raw bytes on disk are encrypted
        with open(enc_path, 'rb') as f:
            disk_content = f.read()

        self.assertTrue(is_encrypted_bytes(disk_content))
        self.assertNotIn(b"%PDF", disk_content[:10])
        self.assertNotIn(b"State Bank of India", disk_content)

        # Decrypt function restores original PDF
        decrypted = decrypt_file_to_bytes(enc_path)
        self.assertEqual(decrypted, pdf_bytes)

    def test_extractor_transparent_decryption(self):
        """PyMuPDF extractor decrypts on the fly and reads text from encrypted disk files."""
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), "CONFIDENTIAL INVOICE: TOTAL DUE INR 45,000")
        pdf_bytes = doc.write()
        doc.close()

        enc_path = self.temp_path / 'uploads' / 'enc_invoice.pdf'
        save_encrypted_file(pdf_bytes, enc_path)

        # Extract text directly from encrypted file path
        res = extract_text_from_pdf(enc_path)
        self.assertTrue(res['success'])
        self.assertIn("CONFIDENTIAL INVOICE", res['text'])
        self.assertIn("45,000", res['text'])

    def test_legacy_unencrypted_file_fallback(self):
        """Pre-existing unencrypted legacy files are read without error."""
        legacy_bytes = b"%PDF-1.4 Legacy raw document content"
        legacy_path = self.temp_path / 'uploads' / 'legacy.pdf'
        with open(legacy_path, 'wb') as f:
            f.write(legacy_bytes)

        # decrypt_file_to_bytes should transparently return the unencrypted bytes
        read_bytes = decrypt_file_to_bytes(legacy_path)
        self.assertEqual(read_bytes, legacy_bytes)


if __name__ == '__main__':
    unittest.main()
