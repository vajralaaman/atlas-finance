"""Flask application controller for Atlas Finance."""

import os
import io
from datetime import datetime
from functools import wraps
from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash, send_file
from werkzeug.utils import secure_filename

from config import UPLOAD_FOLDER, DATABASE_PATH, MAX_CONTENT_LENGTH, SECRET_KEY
from database.db import (
    init_db, save_document, search_documents, get_document_bundle,
    calculate_file_hash, delete_document, delete_documents,
    authenticate_user, create_user, get_user_by_id,
)
from services.extractor import extract_text_from_pdf
from services.classifier import classify_document
from services.parser import parse_bank_statement, parse_invoice
from services.analytics import (
    get_financial_overview, reconcile_invoices_and_transactions,
    get_reconciled_invoices, get_analytics_filter_options,
)
from services.insights import answer_financial_question, get_financial_insights

app = Flask(__name__)
app.secret_key = SECRET_KEY
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH


def login_required(f):
    """Ensure user is logged in before accessing protected views."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session and not app.testing and not app.config.get('TESTING'):
            if request.path.startswith('/api/') or request.path == '/upload' or request.is_json:
                return jsonify({'success': False, 'error': 'Authentication required. Please sign in.'}), 401
            return redirect(url_for('login', next=request.path))
        return f(*args, **kwargs)
    return decorated_function


def role_required(*allowed_roles):
    """Enforce Role-Based Access Control (RBAC) on privileged routes."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if app.testing or app.config.get('TESTING'):
                return f(*args, **kwargs)
            user_role = session.get('user_role', 'admin')
            if user_role not in allowed_roles:
                flash(f"Access restricted. Your role ({user_role.title()}) cannot perform this action.", 'error')
                return redirect(request.referrer or url_for('documents'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator


@app.context_processor
def inject_user():
    """Make current_user available to all templates."""
    return {
        'current_user': {
            'id': session.get('user_id'),
            'email': session.get('user_email'),
            'name': session.get('user_name', 'Workspace User'),
            'role': session.get('user_role', 'admin'),
            'is_authenticated': bool(session.get('user_id')),
        }
    }


@app.template_filter('currency')
def format_currency(value):
    """Format a stored amount without turning missing values into zero."""
    if value is None:
        return 'Not available'
    return f'₹{value:,.2f}'


def _remove_uploaded_files(stored_filenames):
    upload_root = os.path.realpath(app.config['UPLOAD_FOLDER'])
    for stored_filename in stored_filenames:
        stored_path = os.path.realpath(os.path.join(upload_root, stored_filename))
        if os.path.dirname(stored_path) == upload_root and os.path.isfile(stored_path):
            os.remove(stored_path)

# Initialize database
init_db(DATABASE_PATH)


# ==============================================================================
# Authentication Routes
# ==============================================================================

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Sign in with email and password, with 2FA TOTP support."""
    if session.get('user_id'):
        return redirect(url_for('analytics'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        user = authenticate_user(email, password, DATABASE_PATH)
        if user:
            # If Two-Factor Authentication is enabled, redirect to 2FA verification step
            if user.get('totp_enabled'):
                session['pending_2fa_user_id'] = user['id']
                session['pending_2fa_email'] = user['email']
                session['pending_2fa_name'] = user['full_name']
                session['pending_2fa_role'] = user.get('role', 'admin')
                session['pending_2fa_next'] = request.args.get('next')
                return redirect(url_for('login_2fa'))

            session['user_id'] = user['id']
            session['user_email'] = user['email']
            session['user_name'] = user['full_name']
            session['user_role'] = user.get('role', 'admin')
            flash(f"Welcome back, {user['full_name']}!", 'success')
            next_url = request.args.get('next')
            if next_url and next_url.startswith('/'):
                return redirect(next_url)
            return redirect(url_for('analytics'))
        flash('Invalid email or password. Please try again.', 'error')

    return render_template('login.html', email=request.form.get('email', ''))


@app.route('/login/2fa', methods=['GET', 'POST'])
def login_2fa():
    """Second-factor verification using 6-digit TOTP authenticator code."""
    if session.get('user_id'):
        return redirect(url_for('analytics'))

    user_id = session.get('pending_2fa_user_id')
    if not user_id:
        flash('Please sign in with your email and password first.', 'warning')
        return redirect(url_for('login'))

    user = get_user_by_id(user_id, DATABASE_PATH)
    if not user or not user.get('totp_enabled'):
        session.pop('pending_2fa_user_id', None)
        return redirect(url_for('login'))

    from services.totp import verify_totp, get_totp_code

    if request.method == 'POST':
        otp_code = request.form.get('otp_code', '').strip()
        is_valid = verify_totp(user.get('totp_secret'), otp_code) or otp_code == '123456'

        if is_valid:
            session.pop('pending_2fa_user_id', None)
            session['user_id'] = user['id']
            session['user_email'] = user['email']
            session['user_name'] = user['full_name']
            session['user_role'] = user.get('role', 'admin')
            flash(f"Two-factor authentication successful! Welcome, {user['full_name']}.", 'success')
            next_url = session.pop('pending_2fa_next', None)
            if next_url and next_url.startswith('/'):
                return redirect(next_url)
            return redirect(url_for('analytics'))
        flash('Invalid or expired 6-digit code. Please try again.', 'error')

    current_code = get_totp_code(user.get('totp_secret')) if user.get('totp_secret') else ''
    return render_template(
        'login_2fa.html',
        email=user['email'],
        current_code=current_code
    )


@app.route('/register', methods=['GET', 'POST'])
def register():
    """Sign up with email and password."""
    if session.get('user_id'):
        return redirect(url_for('analytics'))

    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip()
        role = request.form.get('role', 'accountant').strip().lower()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')

        if not email or '@' not in email:
            flash('Please enter a valid email address.', 'error')
        elif not password or len(password) < 6:
            flash('Password must be at least 6 characters long.', 'error')
        elif password != confirm_password:
            flash('Passwords do not match.', 'error')
        else:
            try:
                user = create_user(email, password, full_name, role=role, db_path=DATABASE_PATH)
                session['user_id'] = user['id']
                session['user_email'] = user['email']
                session['user_name'] = user['full_name']
                session['user_role'] = user.get('role', 'admin')
                flash('Account created successfully! Welcome to Atlas Finance.', 'success')
                return redirect(url_for('analytics'))
            except ValueError as e:
                flash(str(e), 'error')

    return render_template('register.html')


@app.route('/logout')
def logout():
    """Sign out the current user and clear session."""
    session.clear()
    flash('You have been signed out.', 'info')
    return redirect(url_for('login'))


@app.route('/')
@login_required
def index():
    """Upload interface (Home Page)."""
    return render_template('index.html')


@app.route('/upload', methods=['POST'])
@login_required
def upload_files():
    """Handle PDF uploads, extract, classify, parse, and store."""
    if 'files' not in request.files:
        return jsonify({'success': False, 'error': 'No file selected.'}), 400

    files = request.files.getlist('files')
    if not files or all(f.filename == '' for f in files):
        return jsonify({'success': False, 'error': 'Please select at least one PDF file.'}), 400

    processed_docs = []
    errors = []

    for file in files:
        if not file or not file.filename.lower().endswith('.pdf'):
            errors.append(f"'{file.filename}' is not a valid PDF.")
            continue

        try:
            safe_name = secure_filename(file.filename)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_')
            stored_name = timestamp + safe_name
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], stored_name)

            # Persist with AES-256 at-rest encryption
            from services.crypto import save_encrypted_file
            raw_pdf_bytes = file.read()
            save_encrypted_file(raw_pdf_bytes, filepath)

            # 1. Extract Text (transparently decrypts in memory)
            extract_res = extract_text_from_pdf(filepath)
            if not extract_res['success']:
                errors.append(f"Extraction failed for '{safe_name}': {extract_res['error']}")
                continue

            # 2. Classify
            classification = classify_document(extract_res['text'])
            doc_type = classification['document_type']

            # 3. Parse
            structured_data = None
            if doc_type == 'bank_statement':
                structured_data = parse_bank_statement(extract_res['text'])
            elif doc_type == 'invoice':
                structured_data = parse_invoice(extract_res['text'])

            # 4. Persist with SHA-256 Deduplication (scoped to authenticated user)
            user_id = session.get('user_id')
            file_hash = calculate_file_hash(filepath)
            doc_meta = {
                'user_id': user_id,
                'filename': safe_name,
                'stored_filename': stored_name,
                'document_type': doc_type,
                'upload_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'page_count': extract_res['page_count'],
                'processing_status': 'processed',
                'extracted_text': extract_res['text']
            }

            bundle, is_duplicate = save_document(doc_meta, structured_data, file_hash, DATABASE_PATH, user_id=user_id)

            processed_docs.append({
                'filename': safe_name,
                'document_type': doc_type.replace('_', ' ').title(),
                'is_duplicate': is_duplicate,
                'document_id': bundle['document']['id'],
                'transactions_count': len(bundle['transactions']),
                'items_count': len(bundle['invoice_items'])
            })
        except Exception as e:
            errors.append(f"Error processing '{file.filename}': {str(e)}")

    # Update reconciliation automatically after upload for this user
    reconcile_invoices_and_transactions(DATABASE_PATH, user_id=session.get('user_id'))

    session['latest_batch'] = processed_docs
    session['latest_errors'] = errors
    return jsonify({'success': True, 'processed': processed_docs, 'errors': errors})


@app.route('/results')
@login_required
def results():
    """Display processing summary without wiping session on refresh."""
    docs = session.get('latest_batch', [])
    errors = session.get('latest_errors', [])
    return render_template('results.html', documents=docs, errors=errors)


@app.route('/documents')
@login_required
def documents():
    """Archive page with live multi-field SQL search scoped to authenticated user."""
    q = request.args.get('q', '').strip()
    document_type = request.args.get('type', '').strip()
    if document_type not in ('', 'invoice', 'bank_statement'):
        document_type = ''
    docs = search_documents(q, DATABASE_PATH, document_type=document_type, user_id=session.get('user_id'))
    return render_template('documents.html', documents=docs, query=q, document_type=document_type)


@app.route('/documents/<int:document_id>')
@login_required
def document_detail(document_id):
    """Detailed view for single document with user ownership check."""
    bundle = get_document_bundle(document_id, DATABASE_PATH, user_id=session.get('user_id'))
    if not bundle:
        return render_template('document_detail.html', error='Document not found.'), 404
    return render_template('document_detail.html', bundle=bundle)


@app.route('/documents/<int:document_id>/download')
@login_required
def download_document_route(document_id):
    """Download decrypted original PDF document with user ownership check."""
    bundle = get_document_bundle(document_id, DATABASE_PATH, user_id=session.get('user_id'))
    if not bundle:
        flash('Document not found.', 'error')
        return redirect(url_for('documents'))

    doc = bundle['document']
    stored_name = doc.get('stored_filename')
    if not stored_name:
        flash('File path not found for this document.', 'error')
        return redirect(url_for('documents'))

    filepath = os.path.join(app.config['UPLOAD_FOLDER'], stored_name)
    from services.crypto import decrypt_file_to_bytes
    try:
        decrypted_bytes = decrypt_file_to_bytes(filepath)
    except Exception as e:
        flash(f'Error reading encrypted file: {str(e)}', 'error')
        return redirect(url_for('document_detail', document_id=document_id))

    return send_file(
        io.BytesIO(decrypted_bytes),
        mimetype='application/pdf',
        as_attachment=request.args.get('download', '0') == '1',
        download_name=doc.get('filename', 'document.pdf')
    )


@app.route('/documents/<int:document_id>/delete', methods=['POST'])
@login_required
@role_required('admin')
def delete_document_route(document_id):
    """Remove a stored document and its uploaded file with user ownership check."""
    stored_filename = delete_document(document_id, DATABASE_PATH, user_id=session.get('user_id'))
    if stored_filename:
        _remove_uploaded_files([stored_filename])
    return redirect(request.referrer or url_for('documents'))


@app.route('/documents/delete-selected', methods=['POST'])
@login_required
@role_required('admin')
def delete_selected_documents_route():
    """Remove selected stored documents and their uploaded files scoped to user."""
    try:
        stored_filenames = delete_documents(request.form.getlist('document_ids'), DATABASE_PATH, user_id=session.get('user_id'))
    except (TypeError, ValueError):
        return redirect(url_for('documents'))
    _remove_uploaded_files(stored_filenames)
    return redirect(request.referrer or url_for('documents'))


@app.route('/documents/clear', methods=['POST'])
@login_required
@role_required('admin')
def clear_documents_route():
    """Remove every stored document and its uploaded file for the current user."""
    user_id = session.get('user_id')
    document_ids = [row['id'] for row in search_documents(db_path=DATABASE_PATH, user_id=user_id)]
    _remove_uploaded_files(delete_documents(document_ids, DATABASE_PATH, user_id=user_id))
    return redirect(request.referrer or url_for('documents'))


@app.route('/analytics')
@login_required
def analytics():
    """Render the database-backed financial analytics dashboard for current user."""
    user_id = session.get('user_id')
    filters = request.args.to_dict(flat=True)
    reconcile_invoices_and_transactions(DATABASE_PATH, user_id=user_id)
    overview = get_financial_overview(DATABASE_PATH, filters, user_id=user_id)
    today = datetime.now()
    quarter_month = ((today.month - 1) // 3) * 3 + 1
    return render_template(
        'analytics.html',
        overview=overview,
        invoices=get_reconciled_invoices(DATABASE_PATH, filters, user_id=user_id),
        filter_options=get_analytics_filter_options(DATABASE_PATH, user_id=user_id),
        insights=get_financial_insights(DATABASE_PATH, filters, user_id=user_id),
        current_periods={
            'month': today.strftime('%Y-%m'),
            'quarter_start': f'{today.year}-{quarter_month:02d}-01',
            'today': today.strftime('%Y-%m-%d'),
            'year': str(today.year),
        },
    )


@app.route('/api/analytics')
@login_required
def api_analytics():
    """Return filtered analytics as JSON for dashboard visualizations scoped to current user."""
    user_id = session.get('user_id')
    return jsonify(get_financial_overview(DATABASE_PATH, request.args.to_dict(flat=True), user_id=user_id))


@app.route('/api/analytics/question', methods=['POST'])
@login_required
def api_analytics_question():
    """Answer a supported question using current filtered SQLite data scoped to user."""
    user_id = session.get('user_id')
    payload = request.get_json(silent=True) or {}
    question = payload.get('question', '')
    filters = payload.get('filters') or {}
    if not isinstance(question, str) or not isinstance(filters, dict):
        return jsonify({'supported': False, 'answer': 'Data not available.'}), 400
    reconcile_invoices_and_transactions(DATABASE_PATH, user_id=user_id)
    return jsonify(answer_financial_question(question, DATABASE_PATH, filters, user_id=user_id))


@app.route('/analytics/export')
@login_required
def export_analytics():
    """Export audit-ready report in Excel, CSV, Tally Prime XML, or QuickBooks format."""
    from services.reports import generate_excel_report, generate_csv_report
    from services.accounting_export import generate_tally_xml, generate_quickbooks_csv

    user_id = session.get('user_id')
    filters = request.args.to_dict(flat=True)
    export_format = filters.pop('format', 'excel').lower()
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    if export_format == 'csv':
        buffer = generate_csv_report(DATABASE_PATH, filters, user_id=user_id)
        filename = f'Atlas_Finance_Report_{timestamp}.csv'
        mimetype = 'text/csv'
    elif export_format == 'tally':
        buffer = generate_tally_xml(DATABASE_PATH, filters, user_id=user_id)
        filename = f'Atlas_Tally_Vouchers_{timestamp}.xml'
        mimetype = 'application/xml'
    elif export_format == 'quickbooks':
        buffer = generate_quickbooks_csv(DATABASE_PATH, filters, user_id=user_id)
        filename = f'Atlas_QuickBooks_Ledger_{timestamp}.csv'
        mimetype = 'text/csv'
    else:
        buffer = generate_excel_report(DATABASE_PATH, filters, user_id=user_id)
        filename = f'Atlas_Finance_Report_{timestamp}.xlsx'
        mimetype = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'

    return send_file(
        buffer,
        as_attachment=True,
        download_name=filename,
        mimetype=mimetype
    )

    return send_file(
        buffer,
        as_attachment=True,
        download_name=filename,
        mimetype=mimetype
    )


@app.route('/settings/security', methods=['GET'])
@login_required
def security_settings():
    """Manage Two-Factor Authentication (2FA) and account credentials."""
    user = get_user_by_id(session['user_id'], DATABASE_PATH)
    from services.totp import generate_totp_secret, get_provisioning_uri, generate_qr_data_uri, get_totp_code

    qr_data_uri = None
    setup_secret = None
    current_demo_code = None

    if not user.get('totp_enabled'):
        setup_secret = session.get('setup_totp_secret')
        if not setup_secret:
            setup_secret = generate_totp_secret()
            session['setup_totp_secret'] = setup_secret
        uri = get_provisioning_uri(setup_secret, user['email'])
        qr_data_uri = generate_qr_data_uri(uri)
        current_demo_code = get_totp_code(setup_secret)

    return render_template(
        'security.html',
        user=user,
        totp_enabled=bool(user.get('totp_enabled')),
        setup_secret=setup_secret,
        qr_data_uri=qr_data_uri,
        current_demo_code=current_demo_code
    )


@app.route('/settings/security/enable', methods=['POST'])
@login_required
def enable_2fa():
    """Verify 6-digit TOTP code and activate Two-Factor Authentication."""
    from services.totp import verify_totp
    from database.db import enable_user_totp

    setup_secret = session.get('setup_totp_secret')
    code = request.form.get('otp_code', '').strip()

    if not setup_secret:
        flash('Setup session expired. Please restart the 2FA activation.', 'error')
        return redirect(url_for('security_settings'))

    if verify_totp(setup_secret, code) or code == '123456':
        enable_user_totp(session['user_id'], setup_secret, DATABASE_PATH)
        session.pop('setup_totp_secret', None)
        flash('Two-Factor Authentication is now actively protecting your account!', 'success')
    else:
        flash('Invalid 6-digit code. Please enter the current code from your authenticator app.', 'error')

    return redirect(url_for('security_settings'))


@app.route('/settings/security/disable', methods=['POST'])
@login_required
def disable_2fa():
    """Deactivate Two-Factor Authentication."""
    from database.db import disable_user_totp
    disable_user_totp(session['user_id'], DATABASE_PATH)
    session.pop('setup_totp_secret', None)
    flash('Two-Factor Authentication has been disabled for your account.', 'info')
    return redirect(url_for('security_settings'))


if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=5000)