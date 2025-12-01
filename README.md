# FDA 483 Form Analysis System

A comprehensive AI-powered system for automated processing, classification, and analysis of FDA Form 483 inspection reports. This system leverages OpenAI's GPT models to extract structured data from PDF documents, classify inspection outcomes (OAI/VAI/NAI), identify violations by severity, and map them to relevant FDA Compliance Programs.

## Project Overview

The FDA 483 Form Analysis System automates the labor-intensive process of reviewing FDA inspection reports. It:

- **Automatically downloads** FDA dashboard data and Form 483 PDFs
- **Extracts and processes** inspection observations from PDF documents
- **Classifies** forms using FDA standards (OAI, VAI, NAI)
- **Analyzes violations** by severity (Critical, Significant, Standard)
- **Maps violations** to FDA Compliance Programs
- **Displays results** in an interactive web dashboard

This system is designed for regulatory professionals, compliance officers, and quality assurance teams who need to efficiently process and analyze FDA inspection reports at scale.

## Technology Stack

- **Python 3.8+**: Core programming language
- **OpenAI GPT-4**: AI model for classification and analysis
- **Flask**: Web framework for dashboard
- **Selenium**: Automated web scraping for FDA dashboard
- **PyPDF2**: PDF text extraction
- **Pandas**: Data processing and CSV handling
- **Bootstrap 5**: Frontend framework for dashboard UI

## Features

- **Automated Classification**: Uses OpenAI to classify 483 forms (OAI, VAI, NAI)
- **Violation Analysis**: Identifies and categorizes violations by severity (Critical, Significant, Standard)
- **Compliance Program Mapping**: Links violations to relevant FDA Compliance Programs
- **Fine-tuning Support**: Prepare labeled data for model fine-tuning
- **Interactive Dashboard**: Web-based dashboard for viewing analysis results with firm names, FEI numbers, and detailed violation analysis
- **Batch Processing**: Process multiple 483 forms simultaneously
- **Firm Name Extraction**: Automatically extracts firm names and FEI numbers from PDFs and Excel files

## Installation

1. Install dependencies:
```bash
pip install -r requirements.txt
```

Or use a virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

2. Set up OpenAI API key:
```bash
export OPENAI_API_KEY="your-api-key-here"
```

Or create a `.env` file:
```
OPENAI_API_KEY=your-api-key-here
```

## Quick Start

### 1. Download Dashboard Data and PDFs

First, download the latest FDA dashboard data:
```bash
python fda_dataset_downloader.py
```

**Notes:**
- The script will skip download if CSV already exists. Use `--force` flag to force re-download.
- After downloading, the script automatically keeps only the **2 latest datasets** (newest + previous latest) and deletes older Excel/CSV files to save disk space.
- This downloads the Excel/CSV file with all Form 483 records and converts it to CSV.

Then download the PDFs (with optional limit):
```bash
# Download 10 PDFs (default)
python download_pdfs.py

# Download specific number of PDFs
python download_pdfs.py --limit 50

# Download all PDFs
python download_pdfs.py --limit 0
```

### 2. Process 483 Forms

The system automatically extracts firm names and FEI numbers during processing from:
- CSV data (primary source - most reliable)
- PDF text extraction (regex patterns + OpenAI fallback)

#### Single Form
```bash
python run_analysis.py --pdf downloaded_pdfs/FDA_100757.pdf
```

#### Batch Processing
```bash
python run_analysis.py --folder downloaded_pdfs --output results
```

**Note:** Firm names and FEI numbers are automatically extracted during processing. No separate extraction step needed!

### 3. Update Missing Firm Names and FEI Numbers (Optional)

If some result files have "Unknown" or "N/A" values, update them:
```bash
python fix_firm_names.py
```

This script will:
- Match PDFs to CSV/Excel entries by media ID
- Update result files with data from CSV/Excel
- Reprocess PDFs with improved extraction for missing data
- Extract firm names and FEI numbers using OpenAI if needed

### 4. Start Dashboard

```bash
python dashboard.py
```

Then open your browser to `http://localhost:5000`

## System Architecture

### Core Components

1. **fda_483_processor.py**: Core processor that:
   - Extracts text from PDF forms
   - Identifies observations from 483 forms
   - Calls OpenAI API for classification and violation analysis
   - Generates comprehensive analysis including follow-up actions

2. **dashboard.py**: Flask web application for:
   - Displaying summary of all processed forms
   - Showing detailed violation analysis by severity and compliance program
   - Filtering and searching capabilities
   - Statistics and metrics

3. **run_analysis.py**: Command-line interface for processing forms

4. **fix_firm_names.py**: Utility to extract and update firm names and FEI numbers:
   - Matches PDFs to Excel entries
   - Uses OpenAI to extract firm info from PDFs when Excel data unavailable
   - Updates all result JSON files

5. **finetune_preparation.py**: Tools for:
   - Creating labeled data templates
   - Converting to OpenAI fine-tuning format

6. **download_pdfs.py**: Downloads PDFs from URLs in CSV file

7. **fda_dataset_downloader.py**: Downloads FDA dashboard data:
   - Automates Excel/CSV download from FDA website
   - Converts Excel files to CSV format
   - Skips download if CSV already exists (use `--force` to re-download)
   - Automatically cleans up old files, keeping only the 2 latest datasets (newest + previous latest)

## Output Structure

Each processed form generates a JSON file in the `results` folder with:

- **Overall Classification**: OAI, VAI, or NAI
- **Classification Justification**: Detailed reasoning for classification
- **Relevant Compliance Programs**: List of applicable FDA compliance programs
- **Violations**: Detailed analysis of each observation including:
  - Observation number
  - Classification (Critical/Significant/Standard)
  - Violation code (e.g., 21 CFR 211.xxx)
  - Rationale and risk level
  - Compliance program mapping
  - Repeat violation flags
  - Required actions
- **Follow-up Actions**: Immediate, short-term, and long-term actions
- **Risk Prioritization**: High-priority elements and regulatory meeting topics
- **Documentation Requirements**: FACTS entries and enforcement coordination
- **Metadata**: Firm name, FEI number, processing date, model used

## Dashboard Features

The interactive dashboard provides:

- **Summary Statistics**: Total forms, classification distribution (OAI/VAI/NAI)
- **Summary Table**: All processed forms with:
  - Firm name
  - FEI number
  - Form type
  - Overall classification
  - Relevant compliance programs
  - Violation count
  - Details button
- **Detail View**: Comprehensive violation analysis showing:
  - File information (filename)
  - Overall classification and justification
  - Violations organized by:
    - Severity (Critical, Significant, Standard)
    - Compliance Program Criteria
  - Follow-up actions (immediate, short-term, long-term)
  - Risk prioritization
  - Documentation requirements
- **Search & Filter**: Find specific forms by firm name, FEI, or classification

## FDA Compliance Programs

The system references FDA Compliance Programs including:
- 7356.002 - Drug Manufacturing Inspections
- 7356.008 - Compounding Pharmacy Inspections
- 7346.832 - Sterile Drug Products
- 7356.014 - Drug Quality Assurance
- 7356.001 - Drug GMP Inspections
- 7356.003 - Active Pharmaceutical Ingredient (API) Inspections
- 7346.844 - Non-Sterile Drug Products
- 7356.009 - Human Drug Outlets

Refer to [FDA Compliance Program Manual](https://www.fda.gov/inspections-compliance-enforcement-and-criminal-investigations/compliance-program-manual) for complete details.

## Workflow Example

### Complete Processing Workflow

1. **Download Dashboard Data and PDFs**:
```bash
# Download FDA dashboard data (skips if CSV exists)
python fda_dataset_downloader.py

# Download PDFs (automatically skips already downloaded PDFs)
python download_pdfs.py --limit 50
```

2. **Process all PDFs** (PDFs are automatically deleted after successful JSON extraction):
```bash
python run_analysis.py --folder downloaded_pdfs --output results

# To keep PDFs after processing, use:
python run_analysis.py --folder downloaded_pdfs --output results --keep-pdfs
```

3. **Extract firm names and FEI numbers** (if needed):
```bash
python fix_firm_names.py
```

4. **Start Dashboard**:
```bash
python dashboard.py
```

5. **View Results**: Open `http://localhost:5000` in your browser

## Fine-tuning

- **Status:** No fine-tuning is included in this release. The processing pipeline uses pretrained OpenAI models (via the OpenAI API) for all inference.

- **Notes:** The previous fine-tuning helper (`finetune_preparation.py`) has been archived/removed from the main pipeline. If you choose to fine-tune in the future, prepare a validated labeled dataset (gold or silver), convert it to the OpenAI JSONL chat fine-tuning format, and follow OpenAI's hosted fine-tuning workflow. Contact the repository owner or check project history for archived helper scripts.

## Example Output

```json
{
  "overall_classification": "OAI",
  "classification_justification": "This inspection would clearly result in OAI classification due to the severity and nature of violations, particularly involving sterile drug products.",
  "relevant_compliance_programs": ["7356.002", "7356.008", "7346.832"],
  "violations": [
    {
      "observation_number": 1,
      "classification": "Critical",
      "violation_code": "21 CFR 211.192",
      "rationale": "Sterility failure of Avastin® with inadequate investigation scope",
      "risk_level": "High",
      "compliance_program": "7346.832",
      "is_repeat": false,
      "action_required": "Immediate corrective action required, potential product recall consideration"
    }
  ],
  "metadata": {
    "firm": "RC Outsourcing, LLC",
    "fei": "1234567",
    "processed_date": "2025-11-05T16:47:33.906296",
    "model_used": "gpt-4-turbo-preview"
  }
}
```

## Troubleshooting

### Firm Names or FEI Numbers Missing

If firm names or FEI numbers are showing as "Unknown" or "N/A":
1. Run `fix_firm_names.py` to extract from PDFs and Excel
2. Ensure your Excel file has the correct "Download" URLs matching the PDF media IDs
3. Check that PDFs have readable text (not just images)

### Dashboard Not Showing Data

1. Ensure results JSON files are in the `results` folder
2. Restart the dashboard: `python dashboard.py`
3. Refresh your browser (F5 or Cmd+R)
4. Check that JSON files are valid (no syntax errors)

### PDF Extraction Issues

Some PDFs may have poor text quality:
- The system will attempt extraction but may need manual correction
- Consider using OCR preprocessing for image-based PDFs
- Check PDF text quality by examining the extracted text

### OpenAI API Errors

- Verify your API key is correct and has sufficient credits
- Check API rate limits
- Ensure stable internet connection

## Project Structure

```
FDA-483-Form-Analysis-System/
│
├── Core Processing Scripts
│   ├── fda_483_processor.py          # Core AI processing engine
│   ├── run_analysis.py                # Main CLI for processing forms
│   └── dashboard.py                   # Flask web dashboard application
│
├── Data Acquisition Scripts
│   ├── fda_dataset_downloader.py      # Download FDA dashboard data (Excel/CSV)
│   └── download_pdfs.py               # Download Form 483 PDFs from URLs
│
├── Data Management
│   └── fix_firm_names.py              # Extract and update firm names/FEI numbers
│
├── Model Training
│   └── finetune_preparation.py       # Prepare labeled data for fine-tuning
│
├── Web Interface
│   ├── templates/
│   │   └── dashboard.html             # Dashboard HTML template
│   └── static/                        # Static assets (CSS, JS, images)
│
├── Documentation
│   ├── README.md                      # This file
│   ├── QUICKSTART.md                  # Quick start guide
│   ├── RISK_ASSESSMENT.md             # Risk assessment documentation
│   └── FDA_DASHBOARD_GUIDE.md        # FDA dashboard usage guide
│
├── Configuration
│   ├── requirements.txt               # Python dependencies
│   ├── .gitignore                     # Git ignore rules
│   └── .env                           # Environment variables (create this)
│
└── Data Directories (Git-ignored)
    ├── downloaded_pdfs/               # Downloaded PDF files
    ├── results/                       # Processed JSON results
    ├── fda_outputs/                   # CSV files from dashboard downloader
    ├── fda_dashboard_downloads/       # Temporary download directory
    ├── downloaded_excel/              # Excel download directory
    └── venv/                          # Python virtual environment
```

### Key Directories

- **Core Scripts**: Main processing and analysis logic
- **Data Acquisition**: Scripts for downloading FDA data and PDFs
- **Data Management**: Tools for extracting and updating firm information
- **Web Interface**: Dashboard templates and static files
- **Documentation**: Project documentation and guides
- **Data Directories**: All data directories are git-ignored to keep the repository clean

## Notes

- Ensure you have sufficient OpenAI API credits for processing
- PDF text extraction quality depends on PDF format
- Fine-tuning requires labeled data for best results
- Dashboard requires results JSON files in the `results` folder
- Firm names and FEI numbers are automatically extracted but can be manually updated in result JSON files
