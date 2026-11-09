"""Normalized SQLite schema for Atlas Finance."""

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    filename TEXT NOT NULL,
    stored_filename TEXT,
    document_type TEXT NOT NULL CHECK (document_type IN ('bank_statement', 'invoice', 'unknown')),
    upload_date TEXT NOT NULL,
    page_count INTEGER NOT NULL DEFAULT 0,
    processing_status TEXT NOT NULL,
    extracted_text TEXT NOT NULL DEFAULT '',
    file_hash TEXT NOT NULL,
    bank_name TEXT,
    account_holder TEXT,
    account_number TEXT,
    statement_start_date TEXT,
    statement_end_date TEXT,
    opening_balance REAL,
    closing_balance REAL,
    currency TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL,
    transaction_date TEXT,
    description TEXT,
    debit REAL,
    credit REAL,
    balance REAL,
    category TEXT DEFAULT 'Uncategorized',
    currency TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS invoices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL UNIQUE,
    invoice_number TEXT,
    invoice_date TEXT,
    due_date TEXT,
    vendor_name TEXT,
    customer_name TEXT,
    currency TEXT,
    subtotal REAL,
    tax REAL,
    discount REAL,
    total_amount REAL,
    reconciliation_status TEXT DEFAULT 'PENDING',
    reconciled_transaction_id INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE,
    FOREIGN KEY (reconciled_transaction_id) REFERENCES transactions(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS invoice_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id INTEGER NOT NULL,
    product_or_service TEXT,
    quantity REAL,
    unit_price REAL,
    line_total REAL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (invoice_id) REFERENCES invoices(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    full_name TEXT,
    role TEXT NOT NULL DEFAULT 'admin' CHECK (role IN ('admin', 'accountant', 'auditor')),
    totp_secret TEXT DEFAULT NULL,
    totp_enabled INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_documents_file_hash ON documents(file_hash);
CREATE INDEX IF NOT EXISTS idx_documents_user_id ON documents(user_id);
CREATE INDEX IF NOT EXISTS idx_documents_user_hash ON documents(user_id, file_hash);
CREATE INDEX IF NOT EXISTS idx_transactions_document_id ON transactions(document_id);
CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(transaction_date);
CREATE INDEX IF NOT EXISTS idx_invoices_document_id ON invoices(document_id);
CREATE INDEX IF NOT EXISTS idx_invoice_items_invoice_id ON invoice_items(invoice_id);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
"""
