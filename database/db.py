"""Database operations and persistence layer with Auto-Migration."""

import sys
import hashlib
import sqlite3
from pathlib import Path

# Ensure project root is in sys.path so db.py can be executed or imported from anywhere
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from werkzeug.security import generate_password_hash, check_password_hash

try:
    from config import DATABASE_PATH
except ImportError:
    DATABASE_PATH = PROJECT_ROOT / 'database' / 'financial_documents.db'

try:
    from database.schema import SCHEMA_SQL
except ImportError:
    from schema import SCHEMA_SQL


def get_connection(db_path=DATABASE_PATH):
    """Open a SQLite connection with foreign keys enabled."""
    if isinstance(db_path, sqlite3.Connection):
        return db_path
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path=DATABASE_PATH):
    """Initialize database tables, auto-migrate columns, and seed default user."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    with get_connection(db_path) as conn:
        # Pre-schema migration: ensure existing tables have new columns before index creation
        doc_table = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='documents'").fetchone()
        if doc_table:
            doc_cols = {row['name'] for row in conn.execute("PRAGMA table_info(documents)").fetchall()}
            if 'user_id' not in doc_cols:
                conn.execute("ALTER TABLE documents ADD COLUMN user_id INTEGER REFERENCES users(id) ON DELETE CASCADE")
                conn.execute("UPDATE documents SET user_id = 1 WHERE user_id IS NULL")

        conn.executescript(SCHEMA_SQL)
        _migrate_global_file_hash_constraint(conn)

        # Auto-migration: check and add Phase 4 columns to existing databases
        # 1. Check 'invoices' table columns
        inv_cols = {row['name'] for row in conn.execute("PRAGMA table_info(invoices)").fetchall()}
        if 'reconciliation_status' not in inv_cols:
            conn.execute("ALTER TABLE invoices ADD COLUMN reconciliation_status TEXT DEFAULT 'PENDING'")
        if 'reconciled_transaction_id' not in inv_cols:
            conn.execute("ALTER TABLE invoices ADD COLUMN reconciled_transaction_id INTEGER")

        # 2. Check 'transactions' table columns
        tx_cols = {row['name'] for row in conn.execute("PRAGMA table_info(transactions)").fetchall()}
        if 'category' not in tx_cols:
            conn.execute("ALTER TABLE transactions ADD COLUMN category TEXT DEFAULT 'Uncategorized'")

        # 3. Check 'users' table columns
        user_cols = {row['name'] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
        if 'role' not in user_cols:
            conn.execute("ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'admin'")
        if 'totp_secret' not in user_cols:
            conn.execute("ALTER TABLE users ADD COLUMN totp_secret TEXT DEFAULT NULL")
        if 'totp_enabled' not in user_cols:
            conn.execute("ALTER TABLE users ADD COLUMN totp_enabled INTEGER NOT NULL DEFAULT 0")

        # 4. Seed default demo administrator if users table is empty
        user_count = conn.execute("SELECT COUNT(*) AS count FROM users").fetchone()['count']
        if user_count == 0:
            conn.execute("""
                INSERT INTO users (email, password_hash, full_name, role)
                VALUES (?, ?, ?, 'admin')
            """, ('admin@atlasfinance.com', generate_password_hash('admin123'), 'Admin User'))


def _migrate_global_file_hash_constraint(conn):
    """Replace the legacy global file hash constraint with per-user deduplication."""
    indexes = conn.execute("PRAGMA index_list(documents)").fetchall()
    has_global_unique_hash = any(
        row['unique'] and row['origin'] == 'u'
        and conn.execute(f'PRAGMA index_info("{row["name"]}")').fetchone()['name'] == 'file_hash'
        for row in indexes
    )
    if not has_global_unique_hash:
        return

    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        conn.execute("""
            CREATE TABLE documents_migrated (
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
            )
        """)
        columns = (
            'id', 'user_id', 'filename', 'stored_filename', 'document_type',
            'upload_date', 'page_count', 'processing_status', 'extracted_text',
            'file_hash', 'bank_name', 'account_holder', 'account_number',
            'statement_start_date', 'statement_end_date', 'opening_balance',
            'closing_balance', 'currency', 'created_at'
        )
        column_sql = ', '.join(columns)
        existing_columns = {
            row['name'] for row in conn.execute("PRAGMA table_info(documents)").fetchall()
        }
        defaults = {
            'user_id': 'NULL',
            'stored_filename': 'NULL',
            'bank_name': 'NULL',
            'account_holder': 'NULL',
            'account_number': 'NULL',
            'statement_start_date': 'NULL',
            'statement_end_date': 'NULL',
            'opening_balance': 'NULL',
            'closing_balance': 'NULL',
            'currency': 'NULL',
            'created_at': 'CURRENT_TIMESTAMP',
        }
        source_sql = ', '.join(
            column if column in existing_columns else defaults.get(column, 'NULL')
            for column in columns
        )
        conn.execute(
            f"INSERT INTO documents_migrated ({column_sql}) "
            f"SELECT {source_sql} FROM documents"
        )
        conn.execute("DROP TABLE documents")
        conn.execute("ALTER TABLE documents_migrated RENAME TO documents")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_documents_file_hash ON documents(file_hash)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_documents_user_id ON documents(user_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_documents_user_hash ON documents(user_id, file_hash)")
    finally:
        conn.execute("PRAGMA foreign_keys = ON")


def create_user(email, password, full_name='', db_path=DATABASE_PATH, role='admin'):
    """Register a new user with secure password hashing and assigned role."""
    # Support both create_user(..., db_path, role) and create_user(..., 'auditor')
    if isinstance(db_path, str) and db_path in ('admin', 'accountant', 'auditor'):
        role, db_path = db_path, DATABASE_PATH

    email = (email or '').strip().lower()
    role = role if role in ('admin', 'accountant', 'auditor') else 'admin'
    if not email or '@' not in email:
        raise ValueError('A valid email address is required.')
    if not password or len(password) < 6:
        raise ValueError('Password must be at least 6 characters long.')

    password_hash = generate_password_hash(password)
    with get_connection(db_path) as conn:
        try:
            cursor = conn.execute("""
                INSERT INTO users (email, password_hash, full_name, role)
                VALUES (?, ?, ?, ?)
            """, (email, password_hash, (full_name or '').strip(), role))
            return {
                'id': cursor.lastrowid,
                'email': email,
                'full_name': (full_name or '').strip(),
                'role': role
            }
        except sqlite3.IntegrityError:
            raise ValueError('An account with this email already exists.')


def authenticate_user(email, password, db_path=DATABASE_PATH):
    """Verify user credentials and return user dictionary if valid, else None."""
    email = (email or '').strip().lower()
    if not email or not password:
        return None
    with get_connection(db_path) as conn:
        user = conn.execute(
            "SELECT id, email, password_hash, full_name, role, totp_secret, totp_enabled FROM users WHERE email = ? COLLATE NOCASE",
            (email,)
        ).fetchone()
        if user and check_password_hash(user['password_hash'], password):
            return {
                'id': user['id'],
                'email': user['email'],
                'full_name': user['full_name'] or user['email'].split('@')[0].capitalize(),
                'role': user['role'] if 'role' in user.keys() and user['role'] else 'admin',
                'totp_secret': user['totp_secret'] if 'totp_secret' in user.keys() else None,
                'totp_enabled': bool(user['totp_enabled']) if 'totp_enabled' in user.keys() and user['totp_enabled'] else False,
            }
    return None


def get_user_by_id(user_id, db_path=DATABASE_PATH):
    """Fetch user by id."""
    with get_connection(db_path) as conn:
        user = conn.execute(
            "SELECT id, email, full_name, role, totp_secret, totp_enabled, created_at FROM users WHERE id = ?",
            (user_id,)
        ).fetchone()
        return dict(user) if user else None


def enable_user_totp(user_id, secret, db_path=DATABASE_PATH):
    """Enable 2FA for a user with the verified secret key."""
    with get_connection(db_path) as conn:
        conn.execute(
            "UPDATE users SET totp_secret = ?, totp_enabled = 1 WHERE id = ?",
            (secret.strip(), user_id)
        )


def disable_user_totp(user_id, db_path=DATABASE_PATH):
    """Disable 2FA for a user."""
    with get_connection(db_path) as conn:
        conn.execute(
            "UPDATE users SET totp_secret = NULL, totp_enabled = 0 WHERE id = ?",
            (user_id,)
        )


def calculate_file_hash(file_input):
    """Generate SHA-256 hash to guarantee idempotent uploads (supports path or raw bytes)."""
    digest = hashlib.sha256()
    if isinstance(file_input, (bytes, bytearray)):
        digest.update(file_input)
    elif hasattr(file_input, 'read'):
        for chunk in iter(lambda: file_input.read(1024 * 1024), b''):
            digest.update(chunk)
    else:
        from services.crypto import decrypt_file_to_bytes
        data = decrypt_file_to_bytes(file_input)
        digest.update(data)
    return digest.hexdigest()


def save_document(doc_meta, structured_data, file_hash, db_path=DATABASE_PATH, user_id=None):
    """
    Atomically persist a document and its child tables.
    Returns (bundle, is_duplicate).
    """
    effective_user_id = user_id or doc_meta.get('user_id')
    with get_connection(db_path) as conn:
        # 1. Check for existing file hash (scoped by user if specified)
        if effective_user_id is not None:
            existing = conn.execute(
                "SELECT id FROM documents WHERE file_hash = ? AND user_id = ?",
                (file_hash, effective_user_id)
            ).fetchone()
        else:
            existing = conn.execute(
                "SELECT id FROM documents WHERE file_hash = ?", (file_hash,)
            ).fetchone()

        if existing:
            return get_document_bundle(existing['id'], db_path, conn, user_id=effective_user_id), True

        # 2. Insert document record
        stmt_info = (structured_data or {}).get('statement_information', {}) if structured_data else {}
        cursor = conn.execute(
            """INSERT INTO documents (
                user_id, filename, stored_filename, document_type, upload_date,
                page_count, processing_status, extracted_text, file_hash,
                bank_name, account_holder, account_number,
                statement_start_date, statement_end_date,
                opening_balance, closing_balance, currency
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                effective_user_id,
                doc_meta.get('filename', 'unknown.pdf'),
                doc_meta.get('stored_filename'),
                doc_meta.get('document_type', 'unknown'),
                doc_meta.get('upload_date'),
                doc_meta.get('page_count', 0),
                doc_meta.get('processing_status', 'processed'),
                doc_meta.get('extracted_text', ''),
                file_hash,
                stmt_info.get('bank_name'),
                stmt_info.get('account_holder'),
                stmt_info.get('account_number'),
                stmt_info.get('statement_start_date'),
                stmt_info.get('statement_end_date'),
                stmt_info.get('opening_balance'),
                stmt_info.get('closing_balance'),
                stmt_info.get('currency'),
            ),
        )
        document_id = cursor.lastrowid

        # 3. Insert Bank Transactions if bank statement
        doc_type = doc_meta.get('document_type')
        if doc_type == 'bank_statement' and structured_data:
            currency = stmt_info.get('currency', 'INR')
            for tx in structured_data.get('transactions', []):
                conn.execute(
                    """INSERT INTO transactions (
                        document_id, transaction_date, description,
                        debit, credit, balance, category, currency
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        document_id,
                        tx.get('date'),
                        tx.get('description'),
                        tx.get('debit'),
                        tx.get('credit'),
                        tx.get('balance'),
                        tx.get('category', 'Uncategorized'),
                        currency,
                    ),
                )

        # 4. Insert Invoice & Line Items if invoice
        if doc_type == 'invoice' and structured_data:
            inv_cursor = conn.execute(
                """INSERT INTO invoices (
                    document_id, invoice_number, invoice_date, due_date,
                    vendor_name, customer_name, currency, subtotal,
                    tax, discount, total_amount, reconciliation_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING')""",
                (
                    document_id,
                    structured_data.get('invoice_number'),
                    structured_data.get('invoice_date'),
                    structured_data.get('due_date'),
                    structured_data.get('vendor_name'),
                    structured_data.get('customer_name'),
                    structured_data.get('currency', 'INR'),
                    structured_data.get('subtotal'),
                    structured_data.get('tax'),
                    structured_data.get('discount'),
                    structured_data.get('total_amount'),
                ),
            )
            invoice_id = inv_cursor.lastrowid

            for item in structured_data.get('items', []):
                conn.execute(
                    """INSERT INTO invoice_items (
                        invoice_id, product_or_service, quantity, unit_price, line_total
                    ) VALUES (?, ?, ?, ?, ?)""",
                    (
                        invoice_id,
                        item.get('product_or_service'),
                        item.get('quantity'),
                        item.get('unit_price'),
                        item.get('line_total'),
                    ),
                )

        bundle = get_document_bundle(document_id, db_path, conn, user_id=effective_user_id)
        return bundle, False


def get_document_bundle(document_id, db_path=DATABASE_PATH, conn=None, user_id=None):
    """Retrieve full document bundle including related children, optionally scoped to user."""
    owns_conn = conn is None
    conn = conn or get_connection(db_path)
    try:
        if user_id is not None:
            doc = conn.execute("SELECT * FROM documents WHERE id = ? AND user_id = ?", (document_id, user_id)).fetchone()
        else:
            doc = conn.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
        if not doc:
            return None

        transactions = conn.execute(
            "SELECT * FROM transactions WHERE document_id = ? ORDER BY transaction_date ASC, id ASC",
            (document_id,),
        ).fetchall()

        invoice = conn.execute(
            "SELECT * FROM invoices WHERE document_id = ?", (document_id,)
        ).fetchone()

        invoice_items = []
        if invoice:
            invoice_items = conn.execute(
                "SELECT * FROM invoice_items WHERE invoice_id = ? ORDER BY id ASC",
                (invoice['id'],),
            ).fetchall()

        return {
            'document': dict(doc),
            'transactions': [dict(r) for r in transactions],
            'invoice': dict(invoice) if invoice else None,
            'invoice_items': [dict(r) for r in invoice_items],
        }
    finally:
        if owns_conn:
            conn.close()


def delete_document(document_id, db_path=DATABASE_PATH, user_id=None):
    """Delete one document and return its stored upload filename, verifying ownership."""
    with get_connection(db_path) as conn:
        if user_id is not None:
            document = conn.execute(
                "SELECT stored_filename FROM documents WHERE id = ? AND user_id = ?", (document_id, user_id)
            ).fetchone()
            if not document:
                return None
            conn.execute("DELETE FROM documents WHERE id = ? AND user_id = ?", (document_id, user_id))
        else:
            document = conn.execute(
                "SELECT stored_filename FROM documents WHERE id = ?", (document_id,)
            ).fetchone()
            if not document:
                return None
            conn.execute("DELETE FROM documents WHERE id = ?", (document_id,))
        return document['stored_filename']


def delete_documents(document_ids, db_path=DATABASE_PATH, user_id=None):
    """Delete multiple documents and return their stored upload filenames, scoped to user."""
    ids = sorted({int(document_id) for document_id in document_ids})
    if not ids:
        return []
    placeholders = ','.join('?' for _ in ids)
    with get_connection(db_path) as conn:
        if user_id is not None:
            rows = conn.execute(
                f"SELECT stored_filename FROM documents WHERE id IN ({placeholders}) AND user_id = ?",
                ids + [user_id],
            ).fetchall()
            conn.execute(f"DELETE FROM documents WHERE id IN ({placeholders}) AND user_id = ?", ids + [user_id])
        else:
            rows = conn.execute(
                f"SELECT stored_filename FROM documents WHERE id IN ({placeholders})",
                ids,
            ).fetchall()
            conn.execute(f"DELETE FROM documents WHERE id IN ({placeholders})", ids)
        return [row['stored_filename'] for row in rows if row['stored_filename']]


def search_documents(query="", db_path=DATABASE_PATH, document_type="", user_id=None):
    """Search stored documents across document and invoice tables, scoped to user."""
    query = (query or '').strip()
    document_type = (document_type or '').strip()
    with get_connection(db_path) as conn:
        conditions = []
        params = []
        if user_id is not None:
            conditions.append("d.user_id = ?")
            params.append(user_id)
        if document_type:
            conditions.append("d.document_type = ?")
            params.append(document_type)
        if query:
            term = f"%{query}%"
            conditions.append("""(d.filename LIKE ? OR d.bank_name LIKE ?
                OR d.account_holder LIKE ? OR i.vendor_name LIKE ?
                OR i.invoice_number LIKE ? OR t.description LIKE ?
                OR CAST(i.total_amount AS TEXT) LIKE ?
                OR CAST(t.debit AS TEXT) LIKE ? OR CAST(t.credit AS TEXT) LIKE ?)""")
            params.extend([term] * 9)
        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        sql = f"""
            SELECT DISTINCT d.*, i.invoice_number, i.invoice_date, i.vendor_name,
                            i.total_amount AS invoice_total
            FROM documents d
            LEFT JOIN invoices i ON i.document_id = d.id
            LEFT JOIN transactions t ON t.document_id = d.id
            {where_clause}
            ORDER BY d.created_at DESC, d.id DESC
        """
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
        return [dict(r) for r in rows]


if __name__ == '__main__':
    print(f"Initializing Atlas Finance database at: {DATABASE_PATH}")
    init_db(DATABASE_PATH)
    print("Database initialized successfully.")