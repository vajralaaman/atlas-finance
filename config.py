import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

UPLOAD_FOLDER = BASE_DIR / 'uploads'
DATABASE_PATH = BASE_DIR / 'database' / 'financial_documents.db'
MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50 MB
ALLOWED_EXTENSIONS = {'pdf'}
SECRET_KEY = os.environ.get('SECRET_KEY', 'financial-analyzer-dev-key-2026')

UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)