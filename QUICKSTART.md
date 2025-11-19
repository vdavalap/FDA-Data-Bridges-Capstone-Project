# Quick Start Guide

## Step 1: Install Dependencies

```bash
# Activate virtual environment (if using one)
source venv/bin/activate

# Install required packages
pip install -r requirements.txt
```

## Step 2: Set Up OpenAI API Key

```bash
# Option 1: Set environment variable
export OPENAI_API_KEY="sk-your-api-key-here"

# Option 2: Create .env file
cp .env.example .env
# Then edit .env and add your API key
```

## Step 3: Process a 483 Form

### Single Form
```bash
python run_analysis.py --pdf downloaded_pdfs/FDA_188559.pdf --firm "RC Outsourcing, LLC" --fei "1234567"
```

### Batch Processing
```bash
python run_analysis.py --folder downloaded_pdfs --output results
```

## Step 4: View Results in Dashboard

```bash
# Start the dashboard server
python dashboard.py

# Open browser to:
# http://localhost:5000
```

## Step 5: Fine-tuning (Optional)

1. Create example labeled data:
```bash
python finetune_preparation.py create_example labeled_data.json
```

2. Edit `labeled_data.json` with your labeled examples

3. Prepare dataset:
```bash
python finetune_preparation.py prepare labeled_data.json finetuning_dataset.jsonl
```

4. Upload to OpenAI for fine-tuning (see OpenAI documentation)

## Example Workflow

1. **Download PDFs** (from your Excel file):
```bash
python download_pdfs.py
```

2. **Process all PDFs**:
```bash
python run_analysis.py --folder downloaded_pdfs --output results
```

3. **Start Dashboard**:
```bash
python dashboard.py
```

4. **View Results**: Open http://localhost:5000 in your browser

## Troubleshooting

- **API Key Error**: Make sure OPENAI_API_KEY is set correctly
- **PDF Extraction Issues**: Some PDFs may have poor text quality; consider OCR preprocessing
- **Dashboard Not Loading**: Ensure results JSON files are in the `results` folder
- **Model Errors**: Check OpenAI API status and your account credits

