"""
Fix firm names - extract from CSV or Excel, fallback to PDF extraction
"""

import pandas as pd
import json
import os
import re
from pathlib import Path
from dotenv import load_dotenv
from fda_483_processor import FDA483Processor

# Load environment variables from .env file
load_dotenv()

def extract_media_id_from_url(url):
    """Extract media ID from FDA download URL"""
    if pd.isna(url) or not isinstance(url, str):
        return None
    match = re.search(r'/media/(\d+)/download', url)
    return match.group(1) if match else None

def extract_media_id_from_filename(filename):
    """Extract media ID from PDF filename like FDA_188559.pdf or JSON filename like FDA_188559_result.json"""
    # Try PDF pattern first
    match = re.search(r'FDA_(\d+)\.pdf', filename)
    if match:
        return match.group(1)
    # Try JSON result pattern
    match = re.search(r'FDA_(\d+)_result\.json', filename)
    if match:
        return match.group(1)
    # Try generic pattern (just FDA_ followed by digits)
    match = re.search(r'FDA_(\d+)', filename)
    return match.group(1) if match else None

def create_firm_mapping_from_csv(csv_path):
    """Create mapping from media ID to firm info from CSV (from fda_dataset_downloader.py)"""
    mapping = {}
    try:
        # If directory, find latest CSV
        if os.path.isdir(csv_path):
            csv_files = sorted(
                Path(csv_path).glob("*.csv"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            if csv_files:
                csv_path = str(csv_files[0])
                print(f"Using latest CSV: {csv_path}")
            else:
                print(f"No CSV files found in {csv_path}")
                return mapping
        
        if not os.path.exists(csv_path):
            print(f"CSV file not found: {csv_path}")
            return mapping
        
        df = pd.read_csv(csv_path)
        
        if 'Download' not in df.columns:
            print("CSV missing 'Download' column")
            return mapping
        
        for _, row in df.iterrows():
            media_id = extract_media_id_from_url(row.get('Download', ''))
            if media_id:
                fei = row.get('FEI Number', '')
                if pd.isna(fei):
                    fei = 'N/A'
                elif isinstance(fei, float):
                    fei = f"{int(fei)}"
                else:
                    fei = str(fei).strip()
                
                legal_name = row.get('Legal Name', '')
                if pd.isna(legal_name):
                    legal_name = 'Unknown'
                else:
                    legal_name = str(legal_name).strip()
                
                mapping[media_id] = {
                    'firm': legal_name,
                    'fei': fei
                }
        
        print(f"Loaded {len(mapping)} firm mappings from CSV")
    except Exception as e:
        print(f"Error loading CSV: {e}")
    
    return mapping

def create_firm_mapping_from_excel(excel_file):
    """Create mapping from media ID to firm info from Excel"""
    df = pd.read_excel(excel_file)
    
    mapping = {}
    for _, row in df.iterrows():
        media_id = extract_media_id_from_url(row.get('Download', ''))
        if media_id:
            fei = row.get('FEI Number', '')
            if pd.isna(fei):
                fei = 'N/A'
            elif isinstance(fei, float):
                fei = f"{int(fei)}"
            else:
                fei = str(fei)
            
            legal_name = row.get('Legal Name', '')
            if pd.isna(legal_name):
                legal_name = 'Unknown'
            else:
                legal_name = str(legal_name).strip()
            
            mapping[media_id] = {
                'firm': legal_name,
                'fei': fei
            }
    
    return mapping

def extract_firm_from_pdf(pdf_path, processor):
    """Extract firm name and FEI from PDF using OpenAI"""
    try:
        text = processor.extract_text_from_pdf(pdf_path)
        
        # Use first 2000 characters for firm extraction (usually header area)
        header_text = text[:2000]
        
        # Use OpenAI to extract firm name more accurately
        prompt = f"""Extract the firm name and FEI number from this FDA 483 form header text. 
Return ONLY a JSON object with "firm" and "fei" fields. If not found, use "Unknown" for firm and "N/A" for fei.

Header text:
{header_text}

Return format: {{"firm": "Firm Name", "fei": "1234567890"}}"""
        
        try:
            response = processor.client.chat.completions.create(
                model="gpt-4-turbo-preview",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant. Return only valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                response_format={"type": "json_object"}
            )
            
            result = json.loads(response.choices[0].message.content)
            firm_name = result.get('firm', 'Unknown')
            fei = result.get('fei', 'N/A')
            
            # Clean up firm name
            if firm_name and firm_name != 'Unknown':
                firm_name = firm_name.strip()
                # Remove common artifacts
                firm_name = re.sub(r'\s+', ' ', firm_name)
                if len(firm_name) < 3 or 'STREET' in firm_name.upper() or 'ADDRESS' in firm_name.upper():
                    firm_name = 'Unknown'
            
            return firm_name, fei
            
        except Exception as e:
            print(f"    OpenAI extraction failed, using regex: {e}")
            # Fallback to regex if OpenAI fails
            pass
        
        # Fallback: Try regex patterns
        patterns = [
            r'FIRM\s*NAME[:\s]*([^\n]+?)(?:\n|$)',
            r'Firm\s*Name[:\s]*([^\n]+?)(?:\n|$)',
            r'Legal\s*Name[:\s]*([^\n]+?)(?:\n|$)',
        ]
        
        firm_name = None
        for pattern in patterns:
            match = re.search(pattern, header_text, re.IGNORECASE)
            if match:
                firm_name = match.group(1).strip()
                firm_name = re.sub(r'\s+', ' ', firm_name).strip()
                if firm_name and len(firm_name) > 5:
                    break
        
        # Try to find FEI
        fei_match = re.search(r'FEI\s*[:\s]*(\d{10,})', text, re.IGNORECASE)
        fei = fei_match.group(1) if fei_match else 'N/A'
        
        return firm_name or 'Unknown', fei
        
    except Exception as e:
        print(f"    Error extracting from PDF: {e}")
        return 'Unknown', 'N/A'

def update_result_files(results_folder, firm_mapping, processor):
    """Update all result JSON files with firm information"""
    updated_count = 0
    from_csv_count = 0
    extracted_count = 0
    reprocessed_count = 0
    
    for result_file in Path(results_folder).glob('*_result.json'):
        try:
            # Extract media ID from filename
            media_id = extract_media_id_from_filename(result_file.name)
            
            # Load existing result
            with open(result_file, 'r') as f:
                result = json.load(f)
            
            metadata = result.get('metadata', {})
            current_firm = metadata.get('firm', 'Unknown')
            current_fei = metadata.get('fei', 'N/A')
            
            # Check if we need to update (if current values are Unknown/N/A)
            needs_update = (current_firm == 'Unknown' or current_fei == 'N/A')
            
            firm_name = None
            fei = None
            csv_has_entry = False
            
            # Try to get from mapping first (CSV or Excel) - use CSV data even if N/A/Unknown
            if media_id and media_id in firm_mapping:
                firm_info = firm_mapping[media_id]
                firm_name = firm_info['firm']
                fei = firm_info['fei']
                csv_has_entry = True
                from_csv_count += 1
                print(f"  ✓ {result_file.name}: Using CSV data - {firm_name} (FEI: {fei})")
            
            # Only try PDF extraction if CSV doesn't have the entry AND PDF exists
            if not csv_has_entry:
                pdf_name = result_file.name.replace('_result.json', '.pdf')
                pdf_path = os.path.join('downloaded_pdfs', pdf_name)
                
                if os.path.exists(pdf_path):
                    # If missing data, reprocess the PDF with improved extraction
                    if needs_update:
                        print(f"  Reprocessing PDF: {result_file.name} (missing data, CSV not available)")
                        try:
                            # Reprocess with improved extraction
                            new_result = processor.process_483_form(pdf_path)
                            new_metadata = new_result.get('metadata', {})
                            firm_name = new_metadata.get('firm', 'Unknown')
                            fei = new_metadata.get('fei', 'N/A')
                            
                            # Update the entire result with new classification if needed
                            if firm_name != 'Unknown' or fei != 'N/A':
                                result = new_result  # Use the reprocessed result
                                reprocessed_count += 1
                                print(f"    ✓ Reprocessed: {firm_name} (FEI: {fei})")
                            else:
                                # Fallback to simple extraction
                                firm_name, fei = extract_firm_from_pdf(pdf_path, processor)
                                extracted_count += 1
                                print(f"    Extracted: {firm_name} (FEI: {fei})")
                        except Exception as e:
                            print(f"    ⚠ Reprocessing failed, using simple extraction: {e}")
                            firm_name, fei = extract_firm_from_pdf(pdf_path, processor)
                            extracted_count += 1
                            print(f"    Extracted: {firm_name} (FEI: {fei})")
                    else:
                        # Just extract if not missing
                        firm_name, fei = extract_firm_from_pdf(pdf_path, processor)
                        extracted_count += 1
                        print(f"    Extracted: {firm_name} (FEI: {fei})")
                else:
                    # PDF not found - keep current values or use defaults
                    print(f"  ✗ PDF not found for {result_file.name} (CSV also not available)")
                    firm_name = current_firm if current_firm != 'Unknown' else 'Unknown'
                    fei = current_fei if current_fei != 'N/A' else 'N/A'
            
            # Update metadata - use CSV data even if it's N/A/Unknown (it's the authoritative source)
            if 'metadata' not in result:
                result['metadata'] = {}
            
            # Always update if we have values from CSV (even if N/A/Unknown)
            if csv_has_entry:
                result['metadata']['firm'] = firm_name
                result['metadata']['fei'] = fei
            else:
                # Only update if we have better values than Unknown/N/A
                if firm_name and firm_name != 'Unknown':
                    result['metadata']['firm'] = firm_name
                if fei and fei != 'N/A':
                    result['metadata']['fei'] = fei
            
            # Save updated result
            with open(result_file, 'w') as f:
                json.dump(result, f, indent=2)
            
            updated_count += 1
            
        except Exception as e:
            print(f"  ✗ Error updating {result_file.name}: {e}")
    
    return updated_count, from_csv_count, extracted_count, reprocessed_count

def main():
    results_folder = "results"
    csv_dir = os.environ.get('FDA_OUTPUT_DIR', './fda_outputs')
    excel_file = "44e44d6b-e265-4bb0-a155-2b6c0c8f519a.xlsx"
    
    print("Initializing processor...")
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        print("Error: OPENAI_API_KEY environment variable required")
        return
    processor = FDA483Processor(api_key=api_key)
    
    firm_mapping = {}
    
    # Try CSV first (from fda_dashboard_downloader.py)
    print(f"\nTrying to load CSV from: {csv_dir}")
    csv_mapping = create_firm_mapping_from_csv(csv_dir)
    if csv_mapping:
        firm_mapping = csv_mapping
    else:
        # Fallback to Excel
        print(f"\nCSV not found, trying Excel: {excel_file}")
        if os.path.exists(excel_file):
            excel_mapping = create_firm_mapping_from_excel(excel_file)
            firm_mapping = excel_mapping
            print(f"Found {len(firm_mapping)} firm mappings in Excel")
        else:
            print("Neither CSV nor Excel file found")
    
    if not firm_mapping:
        print("No firm mapping data available. Exiting.")
        return
    
    print(f"\nUpdating result files in {results_folder}...")
    updated_count, from_data_count, extracted_count, reprocessed_count = update_result_files(results_folder, firm_mapping, processor)
    
    print(f"\n✓ Updated {updated_count} result files")
    print(f"  - From CSV/Excel: {from_data_count}")
    print(f"  - Extracted from PDFs: {extracted_count}")
    if reprocessed_count > 0:
        print(f"  - Reprocessed PDFs (with improved extraction): {reprocessed_count}")

if __name__ == "__main__":
    main()

