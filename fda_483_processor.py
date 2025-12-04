"""
FDA 483 Form Processor using OpenAI
Processes 483 forms to generate classification and violation analysis
"""

import os
import json
import pandas as pd
from openai import OpenAI
from typing import Dict, List, Optional
from datetime import datetime
import PyPDF2
import re
import logging
import pathlib
from pathlib import Path

class FDA483Processor:
    """Process FDA 483 forms using OpenAI for classification and violation analysis"""
    
    # FDA Compliance Program mappings
    COMPLIANCE_PROGRAMS = {
        "7356.002": "Drug Manufacturing Inspections",
        "7356.008": "Compounding Pharmacy Inspections",
        "7346.832": "Sterile Drug Products",
        "7356.014": "Drug Quality Assurance",
        "7356.001": "Drug GMP Inspections",
        "7356.003": "Active Pharmaceutical Ingredient (API) Inspections",
        "7346.844": "Non-Sterile Drug Products",
        "7356.009": "Human Drug Outlets",
    }
    
    # Classification categories
    CLASSIFICATIONS = {
        "OAI": "Official Action Indicated",
        "VAI": "Voluntary Action Indicated",
        "NAI": "No Action Indicated"
    }
    
    # Violation severity levels
    VIOLATION_LEVELS = {
        "Critical": "Immediate Action Required",
        "Significant": "Action Required",
        "Standard": "Documentation Required"
    }
    
    def __init__(self, api_key: Optional[str] = None, csv_data_path: Optional[str] = None):
        """Initialize processor with OpenAI API key and optional CSV data path"""
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OpenAI API key required. Set OPENAI_API_KEY environment variable or pass api_key parameter.")
        self.client = OpenAI(api_key=self.api_key)
        self.model = "gpt-4o-mini"
        
        # Load CSV data if provided
        self.csv_mapping = {}
        if csv_data_path:
            self.csv_mapping = self._load_csv_mapping(csv_data_path)
            logging.info(f"Loaded {len(self.csv_mapping)} firm mappings from CSV")
    
    def _extract_media_id_from_filename(self, filename: str) -> Optional[str]:
        """Extract media ID from PDF filename like FDA_189344.pdf"""
        match = re.search(r'FDA_(\d+)\.pdf', filename)
        return match.group(1) if match else None
    
    def _extract_media_id_from_url(self, url: str) -> Optional[str]:
        """Extract media ID from FDA download URL"""
        if not isinstance(url, str):
            return None
        match = re.search(r'/media/(\d+)/download', url)
        return match.group(1) if match else None
    
    def _load_csv_mapping(self, csv_path: str) -> Dict[str, Dict[str, str]]:
        """Load firm info mapping from CSV file (from fda_dashboard_downloader.py output)"""
        mapping = {}
        try:
            # Try to find latest CSV if directory provided
            if os.path.isdir(csv_path):
                csv_files = sorted(
                    Path(csv_path).glob("*.csv"),
                    key=lambda p: p.stat().st_mtime,
                    reverse=True,
                )
                if csv_files:
                    csv_path = str(csv_files[0])
                    logging.info(f"Using latest CSV: {csv_path}")
            
            if not os.path.exists(csv_path):
                logging.warning(f"CSV file not found: {csv_path}")
                return mapping
            
            df = pd.read_csv(csv_path)
            logging.info(f"CSV file loaded: {len(df)} rows, columns: {list(df.columns)}")
            
            # Check for required columns
            if 'Download' not in df.columns:
                logging.warning(f"CSV missing 'Download' column. Available columns: {list(df.columns)}")
                return mapping
            
            # Check for FEI Number and Legal Name columns
            fei_col = 'FEI Number' if 'FEI Number' in df.columns else None
            name_col = 'Legal Name' if 'Legal Name' in df.columns else None
            
            if not fei_col or not name_col:
                logging.warning(f"CSV missing required columns. FEI: {fei_col}, Legal Name: {name_col}")
            
            for idx, row in df.iterrows():
                download_url = row.get('Download', '')
                media_id = self._extract_media_id_from_url(download_url)
                if media_id:
                    # Extract FEI Number
                    fei = row.get('FEI Number', '') if fei_col else ''
                    if pd.isna(fei) or fei == '':
                        fei = 'N/A'
                    elif isinstance(fei, float):
                        fei = f"{int(fei)}"
                    else:
                        fei = str(fei).strip()
                    
                    # Extract Legal Name
                    legal_name = row.get('Legal Name', '') if name_col else ''
                    if pd.isna(legal_name) or legal_name == '':
                        legal_name = 'Unknown'
                    else:
                        legal_name = str(legal_name).strip()
                    
                    mapping[media_id] = {
                        'firm': legal_name,
                        'fei': fei
                    }
                else:
                    logging.debug(f"Row {idx}: Could not extract media ID from URL: {download_url}")
            
            logging.info(f"Loaded {len(mapping)} firm mappings from CSV (out of {len(df)} rows)")
        except Exception as e:
            logging.warning(f"Error loading CSV mapping: {e}")
        
        return mapping
    
    def _extract_firm_and_fei_from_pdf(self, pdf_path: str, text: str) -> Dict[str, str]:
        """Extract firm name and FEI from PDF using OpenAI with improved prompts"""
        firm_info = {'firm': 'Unknown', 'fei': 'N/A'}
        
        # Use first 4000 characters for header (more context)
        header_text = text[:4000]
        
        try:
            # Improved prompt for both firm and FEI extraction
            prompt = f"""Extract the firm name and FEI number from this FDA 483 form header text.

CRITICAL INSTRUCTIONS:
1. Firm Name: 
   - Look for labels like "Firm Name:", "Legal Name:", "Establishment Name:", "Name of Firm:", "Company Name:"
   - Extract ONLY the business/company name - do NOT include addresses, cities, states, ZIP codes, or contact information
   - The firm name is typically a business entity name (5-150 characters)
   - Common suffixes: Inc, LLC, Ltd, Limited, Corporation, Corp, Company, Co, GmbH, Pharmaceuticals, Laboratories
   - If you see multiple lines, the firm name is usually the FIRST complete business name before any address
   
2. FEI Number:
   - Look for "FEI", "FEI Number", "FEI No", "FEI #", "FEI:", "FEI Number:" followed by digits
   - FEI numbers are typically 10 digits (sometimes 9-11 digits)
   - Extract ONLY the digits - no dashes, spaces, periods, or other characters
   - The number should be 9-11 digits long
   - It may appear as: FEI: 1234567890, FEI Number: 1234567890, FEI No. 1234567890

3. Search carefully - the information may be formatted differently or have extra spaces/characters.

4. If you cannot find clear, unambiguous information, return "Unknown" for firm and "N/A" for fei.

Header text (first 4000 characters):
{header_text}

Return ONLY a JSON object with "firm" and "fei" fields. 
- For firm: Return the complete business name (no addresses/contact info), or "Unknown" if not clearly found
- For fei: Return the FEI number as digits only (9-11 digits), or "N/A" if not clearly found

Return format: {{"firm": "Complete Business Name Here", "fei": "1234567890"}}"""
            
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that extracts structured data from FDA forms. Return only valid JSON."},
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
                firm_name = re.sub(r'\s+', ' ', firm_name)
                # Validate firm name
                if len(firm_name) < 3 or 'STREET' in firm_name.upper() or 'ADDRESS' in firm_name.upper() or 'CITY' in firm_name.upper():
                    firm_name = 'Unknown'
                else:
                    firm_info['firm'] = firm_name
            
            # Clean up FEI
            if fei and fei != 'N/A':
                fei_clean = re.sub(r'[^\d]', '', str(fei))
                if len(fei_clean) >= 9:  # Valid FEI should be at least 9 digits
                    firm_info['fei'] = fei_clean
                else:
                    firm_info['fei'] = 'N/A'
            
            logging.info(f"Extracted from PDF: Firm={firm_info['firm']}, FEI={firm_info['fei']}")
            
        except Exception as e:
            logging.warning(f"OpenAI extraction failed: {e}, falling back to regex")
            # Fallback to regex patterns
            patterns = [
                r'FIRM\s*NAME[:\s]*([^\n]+?)(?:\n|$)',
                r'Firm\s*Name[:\s]*([^\n]+?)(?:\n|$)',
                r'Legal\s*Name[:\s]*([^\n]+?)(?:\n|$)',
            ]
            
            for pattern in patterns:
                match = re.search(pattern, header_text, re.IGNORECASE)
                if match:
                    firm_name = match.group(1).strip()
                    firm_name = re.sub(r'\s+', ' ', firm_name)
                    if firm_name and len(firm_name) > 5:
                        firm_info['firm'] = firm_name
                        break
            
            # Try to find FEI with multiple patterns
            fei_patterns = [
                r'FEI\s*(?:Number)?\s*[:\s]*(\d{9,11})',
                r'FEI\s*[:\s]*(\d{10})',
            ]
            for pattern in fei_patterns:
                fei_match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
                if fei_match:
                    firm_info['fei'] = fei_match.group(1)
                    break
        
        return firm_info
    
    def extract_text_from_pdf(self, pdf_path: str) -> str:
        """Extract text from PDF file"""
        try:
            with open(pdf_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                text = ""
                for page in pdf_reader.pages:
                    text += page.extract_text() + "\n"
                return text
        except Exception as e:
            raise Exception(f"Error extracting text from PDF: {str(e)}")
    
    def extract_observations_from_text(self, text: str) -> List[Dict]:
        """Extract observations from 483 form text"""
        observations = []
        # Pattern to find observation numbers and content
        pattern = r'Observation\s+(\d+)[:\.]?\s*(.*?)(?=Observation\s+\d+|$)'
        matches = re.finditer(pattern, text, re.IGNORECASE | re.DOTALL)
        
        for match in matches:
            obs_num = match.group(1)
            obs_content = match.group(2).strip()
            observations.append({
                "number": int(obs_num),
                "content": obs_content[:2000]  # Limit length
            })
        
        return observations
    
    def get_classification_prompt(self, observations: List[Dict], firm_info: Dict) -> str:
        """Generate prompt for OpenAI classification"""
        observations_text = "\n\n".join([
            f"Observation {obs['number']}: {obs['content']}"
            for obs in observations
        ])
        
        prompt = f"""You are an FDA compliance expert analyzing Form 483 inspection observations. 

Firm Information:
- Firm Name: {firm_info.get('firm', 'Not specified')}
- FEI: {firm_info.get('fei', 'Not specified')}
- Form Type: 483

Observations:
{observations_text}

Based on these observations, provide a comprehensive analysis in JSON format with the following structure:

{{
    "overall_classification": "OAI" | "VAI" | "NAI",
    "classification_justification": "Detailed explanation of why this classification was assigned",
    "relevant_compliance_programs": ["7356.002", "7356.008", ...],
    "violations": [
        {{
            "observation_number": 1,
            "classification": "Critical" | "Significant" | "Standard",
            "violation_code": "21 CFR 211.xxx or applicable regulation",
            "rationale": "Explanation of violation classification",
            "risk_level": "High" | "Medium" | "Low",
            "compliance_program": "7356.002",
            "is_repeat": false,
            "action_required": "Description of required action"
        }}
    ],
    "follow_up_actions": {{
        "immediate": ["Action 1", "Action 2"],
        "short_term": ["Action 1", "Action 2"],
        "long_term": ["Action 1", "Action 2"]
    }},
    "risk_prioritization": {{
        "high_priority_elements": ["Element 1", "Element 2"],
        "regulatory_meeting_topics": ["Topic 1", "Topic 2"]
    }},
    "documentation_requirements": {{
        "facts_system_entries": ["Entry 1", "Entry 2"],
        "enforcement_coordination": ["Coordination 1", "Coordination 2"]
    }}
}}

Classification Guidelines:
- OAI (Official Action Indicated): Critical violations, repeat violations, systemic failures, patient safety risks
- VAI (Voluntary Action Indicated): Significant violations that require corrective action but don't pose immediate risk
- NAI (No Action Indicated): Minor violations or no significant issues found

Violation Classification:
- Critical: Sterile product contamination, immediate patient safety risks, failure investigations
- Significant: Environmental monitoring issues, trend analysis failures, quality system deficiencies
- Standard: Documentation issues, laboratory procedures, minor cGMP violations

Return ONLY valid JSON, no additional text."""
        
        return prompt
    
    def classify_with_openai(self, observations: List[Dict], firm_info: Dict) -> Dict:
        """Use OpenAI to classify 483 form observations"""
        prompt = self.get_classification_prompt(observations, firm_info)
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an FDA compliance expert. Always respond with valid JSON only."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,  # Lower temperature for more consistent results
                response_format={"type": "json_object"}
            )
            
            result_text = response.choices[0].message.content
            result = json.loads(result_text)
            
            # Add metadata
            result["metadata"] = {
                "processed_date": datetime.now().isoformat(),
                "model_used": self.model,
                "firm": firm_info.get('firm', ''),
                "fei": firm_info.get('fei', ''),
                "observation_count": len(observations)
            }
            
            return result
            
        except json.JSONDecodeError as e:
            raise Exception(f"Failed to parse OpenAI response as JSON: {str(e)}")
        except Exception as e:
            raise Exception(f"OpenAI API error: {str(e)}")
    
    def process_483_form(self, pdf_path: str, firm_info: Optional[Dict] = None) -> Dict:
        """Process a complete 483 form PDF"""
        if firm_info is None:
            firm_info = {}
        
        # Try to get firm info from CSV mapping first (by media ID from filename)
        pdf_filename = os.path.basename(pdf_path)
        media_id = self._extract_media_id_from_filename(pdf_filename)
        
        if media_id:
            logging.info(f"Extracted media ID '{media_id}' from filename '{pdf_filename}'")
            if media_id in self.csv_mapping:
                csv_info = self.csv_mapping[media_id]
                if not firm_info.get('firm') or firm_info.get('firm') == 'Unknown':
                    firm_info['firm'] = csv_info['firm']
                if not firm_info.get('fei') or firm_info.get('fei') == 'N/A':
                    firm_info['fei'] = csv_info['fei']
                logging.info(f"Using CSV data for {pdf_filename}: Firm={firm_info['firm']}, FEI={firm_info['fei']}")
            else:
                logging.warning(f"Media ID '{media_id}' not found in CSV mapping (CSV has {len(self.csv_mapping)} entries)")
        else:
            logging.warning(f"Could not extract media ID from filename '{pdf_filename}'")
        
        # Extract text from PDF
        text = self.extract_text_from_pdf(pdf_path)
        
        # Extract firm and FEI from PDF text immediately after extraction
        # Use first 6000 characters (header area usually contains this info, expanded for better coverage)
        header_text = text[:6000]
        # Also search in first page more specifically
        first_page_text = text.split('\n\n')[0] if '\n\n' in text else text[:3000]
        
        # Track if we need OpenAI extraction
        need_openai_extraction = False
        
        # Extract firm name with multiple regex patterns (expanded set)
        if not firm_info.get('firm') or firm_info.get('firm') == 'Unknown':
            firm_patterns = [
                # Standard patterns
                r'Firm\s*Name[:\s]*([^\n\r]+?)(?:\n|$|FEI|Record|Date|Establishment)',
                r'Legal\s*Name[:\s]*([^\n\r]+?)(?:\n|$|FEI|Record|Date|Establishment)',
                r'FIRM\s*NAME[:\s]*([^\n\r]+?)(?:\n|$|FEI|Record|Date|Establishment)',
                r'Establishment\s*Name[:\s]*([^\n\r]+?)(?:\n|$|FEI|Record|Date)',
                r'Name\s*of\s*Firm[:\s]*([^\n\r]+?)(?:\n|$|FEI|Record|Date)',
                # Patterns with different spacing
                r'Firm\s*Name\s*[:\-]\s*([^\n\r]+?)(?:\n|$|FEI)',
                r'Legal\s*Name\s*[:\-]\s*([^\n\r]+?)(?:\n|$|FEI)',
                # Patterns that might appear on first line
                r'^([A-Z][A-Za-z0-9\s&\.,\-\(\)]+(?:Inc|LLC|Ltd|Limited|Corporation|Corp|Company|Co|GmbH|Pharmaceuticals?|Laboratories?))',
                # Look for company-like names near the start
                r'(?:Firm|Legal|Establishment)\s*[:\s]+([A-Z][A-Za-z0-9\s&\.,\-\(\)]{10,80}?)(?:\n|FEI|Record)',
            ]
            
            firm_found = False
            # Try header text first
            for pattern in firm_patterns:
                match = re.search(pattern, header_text, re.IGNORECASE | re.MULTILINE)
                if match:
                    firm_name = match.group(1).strip()
                    # Clean up the firm name
                    firm_name = re.sub(r'\s+', ' ', firm_name)
                    # Remove trailing punctuation and common artifacts
                    firm_name = re.sub(r'[,\-\.]+$', '', firm_name).strip()
                    # Validate - must be reasonable length and not contain address keywords
                    if (len(firm_name) > 5 and len(firm_name) < 150 and
                        'STREET' not in firm_name.upper() and 
                        'ADDRESS' not in firm_name.upper() and
                        'CITY' not in firm_name.upper() and
                        'STATE' not in firm_name.upper() and
                        'ZIP' not in firm_name.upper() and
                        'POSTAL' not in firm_name.upper() and
                        not firm_name.upper().startswith('HTTP')):
                        firm_info['firm'] = firm_name
                        logging.info(f"Extracted firm name via regex: {firm_name}")
                        firm_found = True
                        break
            
            # If not found, try first page text
            if not firm_found:
                for pattern in firm_patterns[:6]:  # Use first 6 patterns
                    match = re.search(pattern, first_page_text, re.IGNORECASE | re.MULTILINE)
                    if match:
                        firm_name = match.group(1).strip()
                        firm_name = re.sub(r'\s+', ' ', firm_name)
                        firm_name = re.sub(r'[,\-\.]+$', '', firm_name).strip()
                        if (len(firm_name) > 5 and len(firm_name) < 150 and
                            'STREET' not in firm_name.upper() and 
                            'ADDRESS' not in firm_name.upper()):
                            firm_info['firm'] = firm_name
                            logging.info(f"Extracted firm name via regex (first page): {firm_name}")
                            firm_found = True
                            break
            
            if not firm_found:
                need_openai_extraction = True
                logging.warning(f"Could not extract firm name via regex for {pdf_filename}")
        
        # Extract FEI number with multiple regex patterns (expanded set)
        if not firm_info.get('fei') or firm_info.get('fei') == 'N/A':
            fei_patterns = [
                # Standard FEI patterns
                r'FEI\s*(?:Number)?\s*[:\s]*(\d{9,11})',
                r'FEI\s*[:\s]*(\d{10})',
                r'FEI\s*No[:\s]*(\d{9,11})',
                r'FEI\s*#\s*(\d{9,11})',
                r'FEI\s*Number[:\s]*(\d{9,11})',
                # Look for 10-digit numbers near "FEI" text (more flexible)
                r'FEI[^\d]*(\d{10})',
                r'FEI[^\d]{0,20}(\d{9,11})',
                # Patterns with different spacing
                r'FEI\s*[:\-]\s*(\d{9,11})',
                r'FEI\s*Number\s*[:\-]\s*(\d{9,11})',
                # Look for 10-digit numbers that might be FEI (context-based)
                r'(?:FEI|Establishment)\s*[:\s]+(\d{10})',
            ]
            
            fei_found = False
            # Try header text first
            for pattern in fei_patterns:
                fei_match = re.search(pattern, header_text, re.IGNORECASE | re.MULTILINE)
                if fei_match:
                    fei_value = fei_match.group(1)
                    # Clean to digits only
                    fei_clean = re.sub(r'[^\d]', '', fei_value)
                    if len(fei_clean) >= 9 and len(fei_clean) <= 11:  # Valid FEI should be 9-11 digits
                        firm_info['fei'] = fei_clean
                        logging.info(f"Extracted FEI via regex: {firm_info['fei']}")
                        fei_found = True
                        break
            
            # If not found, search in entire text (FEI might be anywhere)
            if not fei_found:
                for pattern in fei_patterns[:6]:  # Use first 6 patterns
                    fei_match = re.search(pattern, text[:10000], re.IGNORECASE | re.MULTILINE)  # Search first 10k chars
                    if fei_match:
                        fei_value = fei_match.group(1)
                        fei_clean = re.sub(r'[^\d]', '', fei_value)
                        if len(fei_clean) >= 9 and len(fei_clean) <= 11:
                            firm_info['fei'] = fei_clean
                            logging.info(f"Extracted FEI via regex (extended search): {firm_info['fei']}")
                            fei_found = True
                            break
            
            if not fei_found:
                need_openai_extraction = True
                logging.warning(f"Could not extract FEI via regex for {pdf_filename}")
        
        # Use OpenAI extraction if regex failed for either firm or FEI
        if need_openai_extraction:
            try:
                pdf_info = self._extract_firm_and_fei_from_pdf(pdf_path, text)
                
                # Update firm if still missing
                if (not firm_info.get('firm') or firm_info.get('firm') == 'Unknown') and pdf_info.get('firm') and pdf_info['firm'] != 'Unknown':
                    firm_info['firm'] = pdf_info['firm']
                    logging.info(f"Extracted firm name via OpenAI: {firm_info['firm']}")
                
                # Update FEI if still missing
                if (not firm_info.get('fei') or firm_info.get('fei') == 'N/A') and pdf_info.get('fei') and pdf_info['fei'] != 'N/A':
                    firm_info['fei'] = pdf_info['fei']
                    logging.info(f"Extracted FEI via OpenAI: {firm_info['fei']}")
            except Exception as e:
                logging.error(f"OpenAI extraction failed for {pdf_filename}: {e}")
        
        # Extract observations
        observations = self.extract_observations_from_text(text)
        
        if not observations:
            # Fallback: use entire text as single observation
            observations = [{"number": 1, "content": text[:5000]}]
        
        # Classify using OpenAI
        classification_result = self.classify_with_openai(observations, firm_info)
        
        return classification_result
    
    def prepare_finetuning_data(self, labeled_data: List[Dict]) -> List[Dict]:
        """Prepare labeled data for OpenAI fine-tuning"""
        training_data = []
        
        for item in labeled_data:
            observations = item.get('observations', [])
            firm_info = item.get('firm_info', {})
            expected_output = item.get('expected_output', {})
            
            prompt = self.get_classification_prompt(observations, firm_info)
            
            training_data.append({
                "messages": [
                    {"role": "system", "content": "You are an FDA compliance expert. Always respond with valid JSON only."},
                    {"role": "user", "content": prompt},
                    {"role": "assistant", "content": json.dumps(expected_output)}
                ]
            })
        
        return training_data
    
    def save_results(self, result: Dict, output_path: str):
        """Save classification results to JSON file"""
        with open(output_path, 'w') as f:
            json.dump(result, f, indent=2)
    
    def process_batch(self, pdf_folder: str, output_folder: str, firm_info_mapping: Optional[Dict] = None, csv_data_path: Optional[str] = None, delete_pdfs_after_processing: bool = True):
        """Process multiple 483 forms from a folder
        
        Args:
            pdf_folder: Folder containing PDF files
            output_folder: Folder to save JSON results
            firm_info_mapping: Optional mapping of PDF filenames to firm info
            csv_data_path: Optional path to CSV data for firm/FEI extraction
            delete_pdfs_after_processing: If True, delete PDFs after successful JSON extraction (default: True)
        """
        # Load CSV mapping if provided
        if csv_data_path and not self.csv_mapping:
            self.csv_mapping = self._load_csv_mapping(csv_data_path)
        
        results = []
        deleted_count = 0
        
        if not os.path.exists(output_folder):
            os.makedirs(output_folder)
        
        pdf_files = [f for f in os.listdir(pdf_folder) if f.endswith('.pdf')]
        
        for pdf_file in pdf_files:
            pdf_path = os.path.join(pdf_folder, pdf_file)
            firm_info = firm_info_mapping.get(pdf_file, {}) if firm_info_mapping else {}
            
            try:
                print(f"Processing {pdf_file}...")
                result = self.process_483_form(pdf_path, firm_info)
                
                # Save individual result
                output_file = os.path.join(output_folder, f"{pdf_file.replace('.pdf', '')}_result.json")
                self.save_results(result, output_file)
                
                # Delete PDF after successful processing if enabled
                if delete_pdfs_after_processing:
                    try:
                        os.remove(pdf_path)
                        deleted_count += 1
                        print(f"  ✓ Deleted PDF: {pdf_file}")
                    except Exception as e:
                        logging.warning(f"Could not delete PDF {pdf_file}: {e}")
                
                results.append({
                    "file": pdf_file,
                    "result": result,
                    "status": "success",
                    "pdf_deleted": delete_pdfs_after_processing
                })
                
            except Exception as e:
                print(f"Error processing {pdf_file}: {str(e)}")
                results.append({
                    "file": pdf_file,
                    "error": str(e),
                    "status": "error",
                    "pdf_deleted": False
                })
        
        # Save batch summary
        summary_path = os.path.join(output_folder, "batch_summary.json")
        with open(summary_path, 'w') as f:
            json.dump(results, f, indent=2)
        
        if delete_pdfs_after_processing:
            print(f"\n✓ Deleted {deleted_count} PDF files after successful processing")
        
        return results