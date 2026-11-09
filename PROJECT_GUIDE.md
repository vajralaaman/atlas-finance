# Atlas Finance: Project Guide

## 1. What This Project Does

Atlas Finance is a Flask web application for small shopkeepers. It converts PDF bank statements and supplier invoices into useful business information:

- Money received and money spent
- Net cash flow
- Current closing balance from bank statements
- Supplier invoice totals
- Paid and pending invoices
- Transaction categories
- Monthly income and expense trends
- Stored document history
- Extracted transaction and invoice details

The shopkeeper does not need to calculate totals manually in a spreadsheet. The application reads the uploaded PDFs, stores the extracted records in SQLite, and displays the results in the dashboard.

> Important: the current application reads text-based PDFs. Scanned image PDFs may not produce usable data because OCR is not included yet.

---

## 2. The Complete User Workflow

```text
Open application
      |
      v
Upload bank statement or supplier invoice PDF
      |
      v
Validate file and secure filename
      |
      v
Extract text from PDF
      |
      v
Classify document
      |
      +--> Bank statement --> extract transactions and balance information
      |
      +--> Invoice ---------> extract invoice header and line items
      |
      v
Standardize dates, amounts, currencies, and fields
      |
      v
Save document and records in SQLite
      |
      v
Match invoices with bank debit transactions
      |
      v
Show processing result
      |
      v
Open dashboard and understand the business position
```

### What the shopkeeper does

1. Open `http://127.0.0.1:5000/`.
2. Drop one or more PDF files into the upload area, or browse for files.
3. Upload bank statements and supplier invoices together or separately.
4. Wait while the application extracts and stores the data.
5. Review the processing result.
6. Open **Overview** to see the business pulse.
7. Use filters to inspect a month, year, date range, document type, or currency.
8. Open a document from the archive when a number needs verification.
9. Upload new documents regularly so the dashboard remains current.

---

## 3. Installation and First Run

### Prerequisites

- Windows, macOS, or Linux
- Python 3.7 or newer
- pip
- A text-based PDF bank statement or invoice for testing

### Windows setup

Open PowerShell in the project folder:

```powershell
cd "d:\mini project"
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### Start the application

```powershell
python app.py
```

Open this address in a browser:

```text
http://127.0.0.1:5000/
```

The database is created automatically at:

```text
database/financial_documents.db
```

The upload folder is:

```text
uploads/
```

Stop the server with `Ctrl+C`.

---

## 4. Main Screens

### 4.1 Upload screen: `/`

This is the shopkeeper's starting point.

The upload screen explains three outcomes:

1. **Upload once**: files are saved and organized.
2. **See every transaction**: bank statement records are extracted.
3. **Know what is due**: invoices are compared with bank payments.

The page accepts multiple PDF files. The browser shows the selected filenames before processing.

### 4.2 Processing results: `/results`

After upload, the application shows:

- Original filename
- Detected document type
- Whether the document was newly saved or already existed
- Number of extracted transactions or invoice line items
- Link to inspect the full stored document
- Any warning or processing error

A duplicate file is not inserted again. Duplicate detection uses a SHA-256 hash of the uploaded file.

### 4.3 Overview dashboard: `/analytics`

This is the main business screen. It reads records from SQLite and calculates the current totals every time the page loads.

### 4.4 Document archive: `/documents`

The archive lists stored documents and supports search. It is useful when the shopkeeper wants to find the original source of a number.

### 4.5 Document detail: `/documents/<id>`

This page shows the complete stored result for one document, including metadata, structured fields, transactions or invoice information, and extracted text where available.

---

# 5. Dashboard: Complete Explanation

The dashboard is designed to answer four questions quickly:

1. How much money came in?
2. How much money went out?
3. Is cash flow healthy?
4. Which invoices still need attention?

The dashboard uses only stored database records. It does not invent missing values. If a value cannot be calculated, it displays `Not available` or `No data available`.

## 5.1 Dashboard header

The header contains:

- **Financial command center**: identifies the page purpose.
- **Your money, made visible**: explains the dashboard in business language.
- **Live ledger**: indicates that the dashboard is reading the current stored records.
- **Records tracked**: counts stored transactions plus invoices.

This gives the shopkeeper immediate context before looking at individual figures.

## 5.2 Filters: Shape your view

The filter area controls all relevant dashboard calculations.

### Date From

Includes transactions and invoices on or after the selected date.

Example: selecting `2026-04-01` includes records from April 1 onward.

### Date To

Includes transactions and invoices on or before the selected date.

Example: selecting `2026-04-30` shows April records through April 30.

### Month

Shows one month using the `YYYY-MM` value.

Example: `2026-04` shows April 2026.

### Year

Shows records from one year.

### Document Type

Options:

- **All types**: bank statements and invoices
- **Bank Statement**: transaction and cash-flow information
- **Invoice**: invoice and reconciliation information

### Currency

Limits the dashboard to one stored currency, such as INR.

### Apply Filters

Reloads the dashboard with the selected filters.

### Reset

Returns to all available records.

> The transaction filters and invoice filters use the relevant date fields. Transactions use `transaction_date`; invoices use `invoice_date`.

## 5.3 The four main KPI cards

### Total Income

**Meaning:** The total of all stored transaction credits in the selected view.

**Calculation:**

```text
Total Income = SUM(transactions.credit)
```

The card also shows:

- Whether income was recorded
- Number of credit transactions

Income can include sales deposits, salary-like credits, refunds, or other credits extracted from the statement. The exact meaning depends on the bank statement description.

### Total Expenses

**Meaning:** The total of all stored transaction debits in the selected view.

**Calculation:**

```text
Total Expenses = SUM(transactions.debit)
```

The card also shows:

- Whether expenses were recorded
- Number of debit transactions

For a shopkeeper, this can include rent, supplier payments, utilities, transport, wages, and other bank debits.

### Net Cash Flow

**Meaning:** Whether more money came in than went out during the selected view.

**Calculation:**

```text
Net Cash Flow = Total Income - Total Expenses
```

Status meanings:

- **Positive**: more money came in than went out
- **Negative**: more money went out than came in
- **Break-even**: income and expenses are equal

This is a cash-flow measure. It is not the same as profit because invoices, stock value, credit sales, and unpaid bills may not be represented as cash yet.

### Total Invoices

**Meaning:** The number of stored invoices in the selected view.

The card also shows:

- Paid invoice count
- Pending invoice count

Invoice value is shown separately in the invoice overview section.

---

## 5.5 Business pulse

The business pulse is the most practical shopkeeper section.

### Latest closing balance

Shows the closing balance from the latest filtered bank statement.

This is the bank balance recorded by the statement. It is not recalculated from all uploaded documents.

### Transactions reviewed

Shows the total number of stored transactions, split into:

- Money in: credit transactions
- Money out: debit transactions

### Invoice follow-up

Shows the number of pending invoices and the value already matched to payments.

This tells the shopkeeper whether supplier follow-up is needed.

### Next useful step

Prompts the user to upload another current statement or invoice. Regular uploads keep the dashboard up to date.

---

## 5.6 Uploaded documents

This section shows:

- Number of bank statements
- Number of invoices
- Number of other or unknown documents, if any
- Recent uploaded files
- Document type
- Bank, vendor, and statement period details
- Link to inspect a document
- Remove action

Deleting a document also deletes its linked transactions and invoices because the database uses foreign-key cascade behavior.

---

## 5.7 Income vs expenses chart

This bar chart compares monthly income and expenses.

- Green bars represent income.
- Coral bars represent expenses.
- Each month is taken from the transaction date.

Use this chart to answer:

- Which month had the highest income?
- Which month had the highest spending?
- Are expenses growing faster than income?

The chart is generated in `static/js/analytics.js` from the `monthly_trends` data returned by the backend.

## 5.8 Monthly cash-flow chart

This line chart shows three monthly series:

- Income
- Expenses
- Net cash flow

Use it to identify direction over time. A falling net line may mean that costs are increasing, sales are dropping, or the statement period is incomplete.

## 5.9 Income and expense analysis

These panels provide four values:

- Total
- Average transaction amount
- Highest transaction amount
- Transaction count

Average income is calculated only from credit transactions. Average expenses are calculated only from debit transactions.

## 5.10 Monthly analysis table

The table displays, for every month:

- Month
- Income
- Expenses
- Net cash flow

This is useful when exact numbers are needed instead of chart estimates.

## 5.11 Expense distribution

This table groups debit transactions by their stored category.

Examples can include:

- Housing
- Utilities
- Food
- Transport
- Uncategorized

Categories come from the standardization and parser logic. The dashboard does not manually guess a category when the source data is unclear.

## 5.12 Invoice overview and reconciliation

This section shows:

- Invoice count
- Total invoice value
- Average invoice value
- Highest invoice value
- Matched invoice count and amount
- Unmatched invoice count and amount
- Total tax
- Total discount
- Vendor totals
- Invoice-by-invoice reconciliation status

### Matching logic

After upload, the application checks pending invoices against bank debit transactions. A match requires:

- Same amount
- Vendor text appearing in the bank transaction description when vendor text is available

A matched invoice receives `PAID` status. An invoice without a match remains `PENDING`.

This is an automated aid, not a final accounting decision. The shopkeeper should inspect the original documents when a payment is ambiguous.

## 5.13 Bank statement overview

This area shows:

- Number of bank statements
- Number of transactions
- Total income
- Total expenses
- Highest income transaction
- Highest expense transaction
- Bank name
- Account holder
- Statement period
- Opening balance
- Closing balance
- Transactions per statement

## 5.14 Top transactions and top expenses

Top transactions are ordered by amount and show date, description, type, and amount.

Top expenses show the largest debit transactions. This helps a shopkeeper quickly find unusual or important costs.

## 5.15 Recent documents

The dashboard provides a compact list of recently uploaded documents with processing status and document details. This makes it easy to verify where a dashboard number came from.

---

# 6. How the Backend Works

## 6.1 Upload controller

`app.py` owns the upload route:

```text
POST /upload
```

For each file, it:

1. Checks that a file was supplied.
2. Checks the `.pdf` extension.
3. Secures the filename with `secure_filename`.
4. Saves the PDF in `uploads/` with a timestamp prefix.
5. Extracts text using PyMuPDF.
6. Classifies the document.
7. Parses bank statement or invoice fields.
8. Calculates a SHA-256 file hash.
9. Saves the document and child records in SQLite.
10. Adds a processing result to the session.
11. Runs invoice reconciliation.
12. Redirects the browser to `/results`.

## 6.2 Analytics controller

The route is:

```text
GET /analytics
```

It:

1. Reads filter values from the URL.
2. Reconciles pending invoices.
3. Calls `get_financial_overview`.
4. Loads filtered invoice rows.
5. Loads filter options.
6. Loads financial insights.
7. Renders `templates/analytics.html`.

The JSON endpoint is:

```text
GET /api/analytics
```

The chart JavaScript reads the returned `monthly_trends` values.

## 6.3 Analytics service

`services/analytics.py` is the main owner of dashboard calculations.

Important functions:

- `_filter_values`: normalizes filter input.
- `_transaction_where`: builds transaction filter conditions.
- `_invoice_where`: builds invoice filter conditions.
- `get_financial_overview`: calculates dashboard totals and supporting lists.
- `reconcile_invoices_and_transactions`: matches invoices to bank debits.
- `get_reconciled_invoices`: returns invoice rows for the dashboard.
- `get_analytics_filter_options`: returns available years and currencies.

## 6.4 Frontend files

- `templates/base.html`: shared brand header, navigation, and footer.
- `templates/index.html`: upload experience.
- `templates/results.html`: processing outcome.
- `templates/analytics.html`: dashboard layout and data bindings.
- `static/css/style.css`: responsive visual design.
- `static/js/main.js`: upload interactions and AJAX submission.
- `static/js/analytics.js`: question form and Chart.js charts.

---

# 7. Database Structure

The SQLite database contains four main tables.

## documents

Stores the source PDF:

- Filename and stored filename
- Document type
- Upload date
- Processing status
- Extracted raw text
- File hash
- Bank statement metadata
- Currency
- Opening and closing balances

## transactions

Stores bank statement rows:

- Document ID
- Transaction date
- Description
- Debit
- Credit
- Balance
- Category
- Currency

## invoices

Stores invoice headers:

- Document ID
- Invoice number
- Invoice and due dates
- Vendor and customer
- Currency
- Subtotal, tax, discount, total amount
- Reconciliation status
- Matched transaction ID

## invoice_items

Stores individual products or services from an invoice:

- Invoice ID
- Product or service
- Quantity
- Unit price
- Line total

Every child record is linked to its source document. This allows the user to move from a dashboard number back to the original document.

---

# 8. Testing

Run the complete test suite:

```powershell
python -m unittest discover -p "test_*.py"
```

Run only analytics tests:

```powershell
python -m unittest test_analytics.py
```

Run the pipeline smoke test:

```powershell
python smoke_test_phase2.py
```

The tests cover database initialization, stored metrics, monthly values, filters, reconciliation, and document deletion behavior.

---

# 9. Troubleshooting

## Dashboard says no data

1. Confirm that the upload completed successfully.
2. Open `/results` and check for processing errors.
3. Confirm the document was classified as `bank_statement` or `invoice`.
4. Reset dashboard filters.
5. Check that the PDF contains selectable text.

## Values are missing

The source PDF may not contain a readable value, or the parser may not recognize its layout. The application intentionally shows `Not available` rather than inventing a value.

## Closing balance is unavailable

The uploaded bank statement may not contain a recognizable closing balance, or the dashboard may not have a filtered bank statement in the selected date range.

## Invoice is still pending

Check whether the bank statement contains:

- The same payment amount
- A description containing the supplier name
- A transaction date inside the selected filter range

Manual review may be required for partial payments, combined payments, or different supplier names.

## Upload fails

- Confirm the file extension is `.pdf`.
- Confirm the file is smaller than 50 MB.
- Confirm the PDF opens normally.
- Confirm the virtual environment is active.
- Reinstall dependencies with `pip install -r requirements.txt`.

## Port 5000 is busy

Change the port in the last line of `app.py`, for example:

```python
app.run(debug=True, host='127.0.0.1', port=5001)
```

Then open `http://127.0.0.1:5001/`.

---

# 10. Recommended Shopkeeper Routine

For the most useful dashboard:

1. Upload every monthly bank statement.
2. Upload supplier invoices when they are received.
3. Do not upload the same file repeatedly; duplicates are automatically ignored.
4. Open the dashboard after each upload.
5. Check net cash flow first.
6. Check the latest closing balance.
7. Review pending invoices.
8. Review top expenses for unexpected payments.
9. Use the month filter for monthly decisions.
10. Open the source document before acting on an unusual number.

The dashboard is a decision-support tool. It helps the shopkeeper see the current position quickly, while the original PDF remains the source document for verification.

---

# 11. Future Improvements

Useful next features for small businesses would be:

- OCR for scanned PDFs
- CSV and Excel upload
- Sales and purchase categories editable by the shopkeeper
- Manual correction of extracted transactions
- Exportable monthly reports
- Profit estimate based on sales and purchases
- Low-cash warning
- Due-date reminders
- User login and separate shop accounts
- Backup and restore
- Production deployment with HTTPS
