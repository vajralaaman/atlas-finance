"""Accounting Software Integration: Tally Prime XML & QuickBooks CSV Exporters.

Converts reconciled transactions and invoices into official ERP import formats:
1. Tally Prime / Tally.ERP 9 XML (Voucher Import Format)
2. QuickBooks Batch Enter Transactions CSV format
"""

import sys
import io
from pathlib import Path

# Ensure project root is in sys.path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import xml.etree.ElementTree as ET
from xml.dom import minidom
from datetime import datetime
from database.db import get_connection, DATABASE_PATH


def _get_export_data(conn, filters=None, user_id=None):
    """Fetch reconciled transactions and invoices for accounting sync scoped to user."""
    where_tx = "WHERE d.user_id = ?" if user_id is not None else ""
    params_tx = (user_id,) if user_id is not None else ()
    query_tx = f"""
        SELECT 
            t.id, t.transaction_date, t.description, t.debit, t.credit, t.category, t.currency,
            d.filename as source_doc
        FROM transactions t
        JOIN documents d ON t.document_id = d.id
        {where_tx}
        ORDER BY t.transaction_date ASC, t.id ASC
    """
    transactions = conn.execute(query_tx, params_tx).fetchall()

    where_inv = "WHERE d.user_id = ?" if user_id is not None else ""
    params_inv = (user_id,) if user_id is not None else ()
    query_inv = f"""
        SELECT 
            i.id, i.invoice_number, i.vendor_name, i.invoice_date, i.total_amount, 
            i.tax, i.reconciliation_status, i.currency, d.filename as source_doc
        FROM invoices i
        JOIN documents d ON i.document_id = d.id
        {where_inv}
        ORDER BY i.invoice_date ASC, i.id ASC
    """
    invoices = conn.execute(query_inv, params_inv).fetchall()

    return transactions, invoices


def generate_tally_xml(db_path=DATABASE_PATH, filters=None, user_id=None) -> io.BytesIO:
    """Generate standard Tally Prime / Tally.ERP 9 XML format for Voucher Import.
    
    Compatible with Tally's 'Import Data > Vouchers' menu.
    Creates Payment vouchers for debits and Receipt vouchers for credits.
    """
    with get_connection(db_path) as conn:
        transactions, invoices = _get_export_data(conn, filters, user_id=user_id)

    root = ET.Element("ENVELOPE")
    
    # Header
    header = ET.SubElement(root, "HEADER")
    tally_req = ET.SubElement(header, "TALLYREQUEST")
    tally_req.text = "Import Data"

    # Body
    body = ET.SubElement(root, "BODY")
    import_data = ET.SubElement(body, "IMPORTDATA")
    
    # Request Description
    req_desc = ET.SubElement(import_data, "REQUESTDESC")
    report_name = ET.SubElement(req_desc, "REPORTNAME")
    report_name.text = "Vouchers"
    static_vars = ET.SubElement(req_desc, "STATICVARIABLES")
    company = ET.SubElement(static_vars, "SVCURRENTCOMPANY")
    company.text = "Atlas Finance Reconciled Company"

    # Request Data
    req_data = ET.SubElement(import_data, "REQUESTDATA")

    for tx in transactions:
        tally_msg = ET.SubElement(req_data, "TALLYMESSAGE", {"xmlns:UDF": "TallyUDF"})
        
        # Determine Voucher Type: Payment for debit, Receipt for credit
        is_debit = (tx['debit'] is not None and tx['debit'] > 0)
        vch_type = "Payment" if is_debit else "Receipt"
        amount = float(tx['debit'] if is_debit else (tx['credit'] or 0.0))
        
        voucher = ET.SubElement(tally_msg, "VOUCHER", {
            "VCHTYPE": vch_type,
            "ACTION": "Create",
            "OBJVIEW": "Accounting Voucher View"
        })

        # Format date as YYYYMMDD for Tally
        raw_date = tx['transaction_date'] or datetime.now().strftime("%Y-%m-%d")
        tally_date = raw_date.replace("-", "")
        
        vch_date = ET.SubElement(voucher, "DATE")
        vch_date.text = tally_date

        vch_type_name = ET.SubElement(voucher, "VOUCHERTYPENAME")
        vch_type_name.text = vch_type

        vch_num = ET.SubElement(voucher, "VOUCHERNUMBER")
        vch_num.text = f"TX-{tx['id']:05d}"

        vch_ref = ET.SubElement(voucher, "REFERENCE")
        vch_ref.text = f"REF-{tx['id']}"

        vch_narration = ET.SubElement(voucher, "NARRATION")
        desc = tx['description'] or "Bank Transaction"
        category = tx['category'] or "General Expense"
        vch_narration.text = f"{desc} | Category: {category} [Source: {tx['source_doc']}]"

        # Party / Expense Ledger Entry
        ledger_entry_party = ET.SubElement(voucher, "ALLLEDGERENTRIES.LIST")
        ledger_party_name = ET.SubElement(ledger_entry_party, "LEDGERNAME")
        ledger_party_name.text = category if is_debit else "Direct Revenue / Income"
        
        party_positive = ET.SubElement(ledger_entry_party, "ISDEEMEDPOSITIVE")
        party_positive.text = "Yes" if is_debit else "No"

        party_amount = ET.SubElement(ledger_entry_party, "AMOUNT")
        party_amount.text = f"{-amount:.2f}" if is_debit else f"{amount:.2f}"

        # Bank Account Ledger Entry
        ledger_entry_bank = ET.SubElement(voucher, "ALLLEDGERENTRIES.LIST")
        ledger_bank_name = ET.SubElement(ledger_entry_bank, "LEDGERNAME")
        ledger_bank_name.text = "Bank Account"

        bank_positive = ET.SubElement(ledger_entry_bank, "ISDEEMEDPOSITIVE")
        bank_positive.text = "No" if is_debit else "Yes"

        bank_amount = ET.SubElement(ledger_entry_bank, "AMOUNT")
        bank_amount.text = f"{amount:.2f}" if is_debit else f"{-amount:.2f}"

    # Export invoices as Purchase Vouchers
    for inv in invoices:
        tally_msg = ET.SubElement(req_data, "TALLYMESSAGE", {"xmlns:UDF": "TallyUDF"})
        voucher = ET.SubElement(tally_msg, "VOUCHER", {
            "VCHTYPE": "Purchase",
            "ACTION": "Create",
            "OBJVIEW": "Accounting Voucher View"
        })

        raw_date = inv['invoice_date'] or datetime.now().strftime("%Y-%m-%d")
        tally_date = raw_date.replace("-", "")

        vch_date = ET.SubElement(voucher, "DATE")
        vch_date.text = tally_date

        vch_type_name = ET.SubElement(voucher, "VOUCHERTYPENAME")
        vch_type_name.text = "Purchase"

        vch_num = ET.SubElement(voucher, "VOUCHERNUMBER")
        vch_num.text = inv['invoice_number'] or f"INV-{inv['id']}"

        vch_narration = ET.SubElement(voucher, "NARRATION")
        vch_narration.text = f"Supplier Invoice: {inv['vendor_name']} | Status: {inv['reconciliation_status']}"

        inv_amount = float(inv['total_amount'] or 0.0)

        # Supplier ledger
        l1 = ET.SubElement(voucher, "ALLLEDGERENTRIES.LIST")
        l1_name = ET.SubElement(l1, "LEDGERNAME")
        l1_name.text = inv['vendor_name'] or "Sundry Creditors"
        l1_pos = ET.SubElement(l1, "ISDEEMEDPOSITIVE")
        l1_pos.text = "No"
        l1_amt = ET.SubElement(l1, "AMOUNT")
        l1_amt.text = f"{inv_amount:.2f}"

        # Purchase account
        l2 = ET.SubElement(voucher, "ALLLEDGERENTRIES.LIST")
        l2_name = ET.SubElement(l2, "LEDGERNAME")
        l2_name.text = "Purchase Account"
        l2_pos = ET.SubElement(l2, "ISDEEMEDPOSITIVE")
        l2_pos.text = "Yes"
        l2_amt = ET.SubElement(l2, "AMOUNT")
        l2_amt.text = f"{-inv_amount:.2f}"

    # Format pretty XML
    rough_string = ET.tostring(root, 'utf-8')
    reparsed = minidom.parseString(rough_string)
    pretty_xml = reparsed.toprettyxml(indent="  ", encoding="utf-8")

    buf = io.BytesIO()
    buf.write(pretty_xml)
    buf.seek(0)
    return buf


def generate_quickbooks_csv(db_path=DATABASE_PATH, filters=None, user_id=None) -> io.BytesIO:
    """Generate standard QuickBooks Batch Enter Transactions CSV format.
    
    Fields: Date, Transaction Type, Number, Name, Memo, Account, Debit, Credit
    """
    with get_connection(db_path) as conn:
        transactions, invoices = _get_export_data(conn, filters, user_id=user_id)

    output = io.StringIO()
    # QuickBooks Standard CSV Header
    output.write("Date,Transaction Type,Number,Name,Memo,Account,Debit,Credit\n")

    for tx in transactions:
        date_str = tx['transaction_date'] or ""
        tx_num = f"TX-{tx['id']}"
        desc = (tx['description'] or "Transaction").replace(",", " ")
        category = (tx['category'] or "General Expense").replace(",", " ")
        source = (tx['source_doc'] or "").replace(",", " ")
        memo = f"{desc} [{source}]"

        debit = tx['debit'] or 0.0
        credit = tx['credit'] or 0.0

        if debit > 0:
            tx_type = "Check"
            # Split 1: Expense Account
            output.write(f"{date_str},{tx_type},{tx_num},{desc},{memo},{category},{debit:.2f},\n")
            # Split 2: Bank Account
            output.write(f"{date_str},{tx_type},{tx_num},{desc},{memo},Bank Account,,{debit:.2f}\n")
        elif credit > 0:
            tx_type = "Deposit"
            # Split 1: Bank Account
            output.write(f"{date_str},{tx_type},{tx_num},{desc},{memo},Bank Account,{credit:.2f},\n")
            # Split 2: Revenue Account
            output.write(f"{date_str},{tx_type},{tx_num},{desc},{memo},Direct Revenue,,{credit:.2f}\n")

    # Invoices
    for inv in invoices:
        date_str = inv['invoice_date'] or ""
        inv_num = inv['invoice_number'] or f"INV-{inv['id']}"
        vendor = (inv['vendor_name'] or "Supplier").replace(",", " ")
        total = inv['total_amount'] or 0.0
        memo = f"Supplier Invoice - {inv['reconciliation_status']}"
        output.write(f"{date_str},Bill,{inv_num},{vendor},{memo},Accounts Payable,,{total:.2f}\n")

    buf = io.BytesIO()
    buf.write(output.getvalue().encode('utf-8'))
    buf.seek(0)
    return buf
