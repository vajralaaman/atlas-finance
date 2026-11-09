# Atlas Finance

## Project Overview

**Atlas Finance** is a college project designed to analyze financial documents such as bank statements and invoices. This repository currently includes the working foundation from Phase 1 and the Phase 2 workflow for document understanding and structured extraction.

## Phase 1: Foundation and PDF Extraction

✅ **Document Upload**
- Upload single or multiple PDF files at once
- Drag-and-drop interface
- Browse files functionality
- Multiple file selection support

✅ **Text Extraction**
- Extract text from PDF documents using PyMuPDF
- Process both bank statements and invoices
- Display text organized by page
- Handle various PDF formats

✅ **Results Display**
- Show extracted text with page-by-page breakdown
- Display document information (filename, pages, file size, upload time)
- User-friendly results page with document cards

✅ **Error Handling**
- Reject non-PDF files
- Handle corrupted PDFs
- Handle empty PDFs
- Handle PDFs with no extractable text
- Display friendly error messages
- Validate file sizes
- Prevent dangerous filenames

✅ **Security**
- Secure filename handling
- File extension validation
- File size limits (50 MB)
- No execution of uploaded files
- Uploads stored safely outside templates/static

✅ **User Interface**
- Clean, professional home page
- Responsive design
- Mobile-friendly layout
- Simple navigation
- Clear buttons and instructions

## Phase 2: Document Understanding and Structured Extraction

✅ **Document Classification**
- Automatically identifies the document type as bank statement, invoice, or unknown
- Uses a rule-based classifier as the default mechanism
- Supports an optional AI hook through environment variables when configured

✅ **Structured Extraction**
- Extracts bank statement metadata such as statement dates, account holder, account number, and currency
- Extracts invoice metadata such as invoice number, dates, totals, customer, and vendor
- Captures transaction or line-item details where the PDF text makes them visible

✅ **Validation and Privacy**
- Validates extracted data quality before presentation
- Masks account numbers for privacy in the UI
- Keeps raw extracted text visible for review and comparison

✅ **Results Presentation**
- Displays both extracted text and the structured output on the same results card
- Shows a compact summary of key fields for each processed document
- Keeps the workflow focused on document understanding without adding financial analysis features

## Phase 3: Database, Validation, and Standardization

✅ **SQLite persistence**
- Stores documents, bank transactions, invoices, and invoice items in `database/financial_documents.db`
- Links every financial record to its source document with foreign keys
- Stores the original extracted text for verification

✅ **Validation and standardization**
- Reuses Phase 2 normalization for common field names, `YYYY-MM-DD` dates, currencies, and numeric amounts
- Invalid dates and non-numeric amounts are stored as `NULL`; values are never invented
- Account numbers remain masked

✅ **Duplicate prevention and retrieval**
- SHA-256 file hashes make repeated processing idempotent
- The `/documents` page lists saved documents
- The `/documents` page supports parameterized search across filenames, document types, invoice fields, transaction fields, dates, and amounts
- `/documents/<id>` displays stored structured data
- JSON retrieval endpoints are available at `/api/documents/<id>`, `/documents/<id>/transactions`, and `/documents/<id>/invoice`

### Phase 3 Data Flow

```
PDF upload -> text extraction -> classification -> structured extraction
           -> validation/standardization -> SQLite transaction -> search/retrieval
```

### Database Tables

- `documents`: uploaded file metadata, type, status, hash, and raw extracted text
- `transactions`: normalized bank transactions linked to `documents`
- `invoices`: normalized invoice headers linked to `documents`
- `invoice_items`: invoice line items linked to `invoices`

The database is initialized automatically when `app.py` starts. To initialize it without starting the server:

```bash
python -c "from database.db import init_db; init_db()"
```

Run the application with `python app.py`, upload a PDF, then open `http://127.0.0.1:5000/documents`. Restart the application and refresh that page to verify persistence. The Phase 2 smoke test can be run with `python smoke_test_phase2.py`.

## Optional AI Configuration

The project includes a safe optional AI integration point. If you want to connect a future LLM API, copy the sample values from [.env.example](.env.example) and set:

- `AI_API_KEY`
- `AI_API_BASE_URL`
- `AI_MODEL_NAME`

If those values are not set, the app remains purely rule-based and does not pretend to use AI when none is configured.

## Phase 4 and Phase 5: Financial Analytics Dashboard

The application now calculates analytics from SQLite data already stored during processing. The `/analytics` page and `/api/analytics` endpoint support date range, month, year, document type, and currency filters without reopening PDFs.

Implemented metrics include total credits and debits, income and expense counts/averages/highs, net cash flow, monthly trends, stored expense categories, top debit transactions, invoice totals/tax/discount, vendor totals, matched and unmatched reconciliation amounts, and recent document links. Chart.js renders income-versus-expense and monthly cash-flow charts from the filtered API data. Empty or missing values are shown as `No data available` or `Not available` rather than being invented.

Focused analytics tests are available with:

```bash
python -m unittest test_analytics.py
```

## Current Scope

This project currently covers:
- PDF upload and extraction
- Document type detection
- Structured field extraction
- Validation, standardization, SQLite storage, and retrieval
- Database-backed financial analytics and responsive dashboard visualizations
- Invoice-to-bank reconciliation presentation

It does not include Phase 6 features such as AI-generated insights, natural-language financial questions, recommendations, fraud detection, or advanced anomaly detection.

## Technologies Used

- **Backend**: Python 3.x, Flask 3.0.0
- **PDF Processing**: PyMuPDF (fitz) 1.23.8
- **Frontend**: HTML5, CSS3, Vanilla JavaScript
- **Database**: SQLite (Phase 3)
- **Server**: Flask development server

## Project Structure

```
AI-Financial-Document-Analyzer/
│
├── app.py                   # Main Flask application
├── requirements.txt         # Python dependencies
├── README.md               # This file
├── .gitignore              # Git ignore rules
│
├── uploads/                # Uploaded PDF files (created automatically)
│
├── templates/              # HTML templates
│   ├── base.html          # Base template with navigation
│   ├── index.html         # Home page with upload interface
│   └── results.html       # Results page with extracted text
│
└── static/                 # Static files
    ├── css/
    │   └── style.css      # CSS styling
    └── js/
        └── script.js      # JavaScript functionality
```

## Installation

### Prerequisites
- Python 3.7 or higher
- pip (Python package manager)

### Setup Steps

1. **Clone or download this project**

2. **Create a virtual environment**
   ```bash
   python -m venv venv
   ```

3. **Activate the virtual environment**

   **Windows:**
   ```bash
   venv\Scripts\activate
   ```

   **macOS/Linux:**
   ```bash
   source venv/bin/activate
   ```

4. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

## Running the Application

1. **Ensure the virtual environment is activated** (see Setup Step 3)

2. **Start the Flask development server**
   ```bash
   python app.py
   ```

3. **Open your browser and navigate to:**
   ```
   http://127.0.0.1:5000/
   ```

4. **The application should now be running locally**

The Flask server will display output showing that it's running. You should see something like:
```
 * Running on http://127.0.0.1:5000
 * Press CTRL+C to stop the server
```

## How to Use Phase 1

### Upload PDF Files

1. **Open the Home Page**
   - Navigate to `http://127.0.0.1:5000/`
   - You will see the upload interface

2. **Upload PDF Files (Multiple Ways)**
   - **Drag & Drop**: Drag PDF files onto the designated area
   - **Browse**: Click "Browse Files" button to select files from your computer
   - **Select Multiple**: Hold Ctrl (Windows/Linux) or Cmd (macOS) to select multiple files

3. **View Selected Files**
   - Selected file names are displayed below the upload area
   - Clear selected files with the "Clear" button if needed

4. **Upload and Process**
   - Click the "Upload" button
   - The application will:
     - Validate the files (PDF only)
     - Save them securely
     - Extract text from each PDF
     - Redirect you to the results page

5. **View Results**
   - See extracted text for each document
   - View document information (pages, file size, upload time)
   - Each document is shown in a separate card
   - Download extracted text (if implemented in future phases)

6. **Return to Upload**
   - Click "Back to Upload" to upload more documents

## Current Limitations (Phase 1)

❌ **Not Implemented Yet**
- No AI analysis of documents
- No document classification (can't determine if file is bank statement vs invoice)
- No financial calculations
- No structured data extraction
- No dashboard or charts
- No transaction categorization
- No anomaly detection
- No OCR (scanned/image-only PDFs cannot be read)
- No database storage
- No chatbot or Q&A functionality
- No report generation

✅ **Currently Supports**
- Text-based PDFs only
- Simple text extraction
- File validation and error handling
- Multiple file uploads
- Basic file information display

## Future Phases

### Phase 2: Document Classification and Structure Extraction
- Identify document type (bank statement, invoice, etc.)
- Extract structured information:
  - Account numbers
  - Transaction dates
  - Amounts
  - Recipient/Payer names
- Implement basic parsing rules

### Phase 4: Financial Analysis
- Transaction categorization
- Income vs. expense analysis
- Time-series analysis
- Anomaly detection
- Basic statistics

### Phase 5: Dashboard and Visualization
- Summary statistics
- Charts and graphs
- Transaction timeline
- Category breakdowns
- Export functionality

### Phase 6: AI-Powered Insights
- Natural language processing
- Q&A interface
- Intelligent pattern detection
- Fraud detection
- Financial recommendations

### Phase 7: Testing, Security & Deployment
- Comprehensive unit tests
- Security audit and hardening
- Performance optimization
- Deployment guide
- Production setup

## Troubleshooting

### "No module named 'flask'"
- Ensure virtual environment is activated
- Run `pip install -r requirements.txt` again

### "No module named 'fitz'"
- Ensure PyMuPDF is installed: `pip install PyMuPDF`

### Port 5000 already in use
- Edit `app.py` and change port number in the last line:
  ```python
  app.run(debug=True, host='127.0.0.1', port=5001)  # Changed to 5001
  ```

### PDF text not extracting
- Ensure the PDF is text-based (not a scanned image)
- Try opening the PDF in a text editor to verify it contains text
- Scanned PDFs will be supported in Phase 2 with OCR

### Files not uploading
- Check file is actually a PDF (`.pdf` extension)
- Ensure file size is under 50 MB
- Check that `uploads/` folder exists (created automatically)

## Security Notes

Even though this is a college prototype:
- ✅ Filenames are secured against path traversal
- ✅ File extensions are validated
- ✅ Upload size is limited
- ✅ Uploaded files are not executed
- ✅ Financial documents are not committed to Git
- ⚠️ Use HTTPS in production
- ⚠️ Implement user authentication for real use
- ⚠️ Add rate limiting
- ⚠️ Encrypt sensitive data at rest

## Developer Notes

### Key Files

- **app.py**: Main Flask application with routes for upload, processing, and results
- **base.html**: Navigation and layout structure
- **index.html**: Upload interface with drag-and-drop
- **results.html**: Display extracted text and document info
- **style.css**: Professional, responsive styling
- **script.js**: Client-side file handling and UI interactions

### Code Quality

- Comments explain key functions for beginners
- Functions are separated for clarity
- Flask routes are well-organized
- Error messages are user-friendly
- No unnecessary frameworks
- Clean, readable code

## Author Notes

This project is designed for:
- Learning Flask web development
- Understanding PDF processing
- Building secure file upload systems
- Creating user-friendly interfaces
- Progressive feature development

## License

This is a college project. Feel free to use and modify for educational purposes.

## Support

For questions or issues:
1. Check the Troubleshooting section
2. Review the code comments
3. Check Flask and PyMuPDF documentation
4. Verify file permissions on the `uploads/` folder

---

**Happy coding! 🚀**
