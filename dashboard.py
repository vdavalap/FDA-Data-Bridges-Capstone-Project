"""
Dashboard for displaying FDA 483 Form Analysis Results
Web-based dashboard using Flask
"""

from flask import Flask, render_template, jsonify, request
import json
import os
import re
from pathlib import Path
from typing import List, Dict
from datetime import datetime
import pandas as pd

app = Flask(__name__)

class FDADashboard:
    """Dashboard for FDA 483 form analysis"""
    
    def __init__(self, results_folder: str = "results"):
        self.results_folder = results_folder
        self.results_cache = {}
        self.csv_data = {}  # Mapping of media_id -> {publish_date, download_url}
        self.load_results()
        self.load_csv_data()
    
    def load_results(self):
        """Load all results from JSON files"""
        if not os.path.exists(self.results_folder):
            return
        
        for file in os.listdir(self.results_folder):
            if file.endswith('_result.json'):
                filepath = os.path.join(self.results_folder, file)
                try:
                    with open(filepath, 'r') as f:
                        data = json.load(f)
                        # Extract identifier from filename
                        identifier = file.replace('_result.json', '')
                        self.results_cache[identifier] = data
                except Exception as e:
                    print(f"Error loading {file}: {e}")
    
    def load_csv_data(self):
        """Load CSV data to get publish dates"""
        csv_dir = os.environ.get('FDA_OUTPUT_DIR', './fda_outputs')
        try:
            if os.path.isdir(csv_dir):
                csv_files = sorted(
                    Path(csv_dir).glob("*.csv"),
                    key=lambda p: p.stat().st_mtime,
                    reverse=True,
                )
                if csv_files:
                    csv_path = str(csv_files[0])
                    df = pd.read_csv(csv_path)
                    
                    # Extract media ID, publish date, and download URL from CSV
                    if 'Download' in df.columns and 'Publish Date' in df.columns:
                        for _, row in df.iterrows():
                            download_url = row.get('Download', '')
                            # Extract media ID from URL
                            match = re.search(r'/media/(\d+)/download', str(download_url))
                            if match:
                                media_id = match.group(1)
                                publish_date = row.get('Publish Date', '')
                                download_url_str = str(download_url).strip() if pd.notna(download_url) else ''
                                
                                self.csv_data[media_id] = {
                                    'publish_date': str(publish_date).strip() if pd.notna(publish_date) else '',
                                    'download_url': download_url_str
                                }
        except Exception as e:
            print(f"Warning: Could not load CSV data for publish dates: {e}")
    
    def _extract_media_id_from_identifier(self, identifier: str) -> str:
        """Extract media ID from identifier like FDA_189489"""
        match = re.search(r'FDA_(\d+)', identifier)
        return match.group(1) if match else None
    
    def get_summary_data(self) -> List[Dict]:
        """Get summary data for all 483 forms"""
        summary = []
        
        for identifier, result in self.results_cache.items():
            metadata = result.get('metadata', {})
            
            # Get compliance programs from top-level field
            compliance_programs = result.get('relevant_compliance_programs', [])
            
            # If empty, extract from violations
            if not compliance_programs or (isinstance(compliance_programs, list) and len(compliance_programs) == 0):
                violations = result.get('violations', [])
                compliance_programs = []
                for violation in violations:
                    program = violation.get('compliance_program')
                    if program and program not in compliance_programs and program != 'Other':
                        compliance_programs.append(program)
            
            # Get publish date from CSV data
            media_id = self._extract_media_id_from_identifier(identifier)
            csv_info = self.csv_data.get(media_id, {}) if media_id else {}
            if isinstance(csv_info, dict):
                publish_date = csv_info.get('publish_date', '')
            else:
                # Backward compatibility: if csv_info is a string (old format)
                publish_date = csv_info if media_id else ''
            
            summary.append({
                "id": identifier,
                "firm": metadata.get('firm', 'Unknown'),
                "fei": metadata.get('fei', 'N/A'),
                "form_type": "483",
                "overall_classification": result.get('overall_classification', 'N/A'),
                "classification_justification": result.get('classification_justification', ''),
                "relevant_compliance_programs": compliance_programs if compliance_programs else [],
                "violation_count": len(result.get('violations', [])),
                "processed_date": metadata.get('processed_date', ''),
                "publish_date": publish_date
            })
        
        # Sort by publish date (newest first), then by processed_date if publish_date is missing
        def sort_key(item):
            publish_date = item.get('publish_date', '')
            if publish_date:
                try:
                    # Try to parse the date
                    return datetime.strptime(publish_date.split()[0], '%Y-%m-%d')
                except:
                    return datetime.min
            # Fallback to processed_date
            processed = item.get('processed_date', '')
            if processed:
                try:
                    return datetime.fromisoformat(processed.replace('Z', '+00:00'))
                except:
                    return datetime.min
            return datetime.min
        
        summary.sort(key=sort_key, reverse=True)
        
        return summary
    
    def get_detail_data(self, identifier: str) -> Dict:
        """Get detailed analysis for a specific 483 form"""
        if identifier not in self.results_cache:
            return None
        
        result = self.results_cache[identifier]
        metadata = result.get('metadata', {})
        
        # Get compliance programs from top-level field
        compliance_programs = result.get('relevant_compliance_programs', [])
        
        # Organize violations by compliance program
        violations_by_program = {}
        for violation in result.get('violations', []):
            program = violation.get('compliance_program', 'Other')
            if program not in violations_by_program:
                violations_by_program[program] = []
            violations_by_program[program].append(violation)
            
            # If compliance programs list is empty, extract from violations
            if program and program != 'Other' and program not in compliance_programs:
                compliance_programs.append(program)
        
        # Group violations by severity
        violations_by_severity = {
            "Critical": [],
            "Significant": [],
            "Standard": []
        }
        
        for violation in result.get('violations', []):
            severity = violation.get('classification', 'Standard')
            violations_by_severity[severity].append(violation)
        
        # Get download URL from CSV data
        media_id = self._extract_media_id_from_identifier(identifier)
        csv_info = self.csv_data.get(media_id, {}) if media_id else {}
        download_url = csv_info.get('download_url', '') if isinstance(csv_info, dict) else ''
        
        return {
            "identifier": identifier,
            "filename": f"{identifier}.pdf",
            "download_url": download_url,
            "metadata": metadata,
            "overall_classification": result.get('overall_classification'),
            "classification_justification": result.get('classification_justification'),
            "relevant_compliance_programs": compliance_programs if compliance_programs else [],
            "violations_by_program": violations_by_program,
            "violations_by_severity": violations_by_severity,
            "follow_up_actions": result.get('follow_up_actions', {}),
            "risk_prioritization": result.get('risk_prioritization', {}),
            "documentation_requirements": result.get('documentation_requirements', {})
        }

# Initialize dashboard
dashboard = FDADashboard()

@app.route('/')
def index():
    """Main dashboard page"""
    return render_template('dashboard.html')

@app.route('/api/summary')
def get_summary():
    """API endpoint for summary data"""
    summary = dashboard.get_summary_data()
    return jsonify(summary)

@app.route('/api/details/<identifier>')
def get_details(identifier):
    """API endpoint for detailed analysis"""
    details = dashboard.get_detail_data(identifier)
    if details is None:
        return jsonify({"error": "Not found"}), 404
    return jsonify(details)

@app.route('/api/stats')
def get_stats():
    """API endpoint for statistics"""
    summary = dashboard.get_summary_data()
    
    if not summary:
        return jsonify({
            "total_forms": 0,
            "classifications": {},
            "violation_counts": {}
        })
    
    # Classification counts
    classifications = {}
    for item in summary:
        classification = item.get('overall_classification', 'Unknown')
        classifications[classification] = classifications.get(classification, 0) + 1
    
    # Violation counts
    violation_counts = {
        "Critical": 0,
        "Significant": 0,
        "Standard": 0
    }
    
    for identifier, result in dashboard.results_cache.items():
        for violation in result.get('violations', []):
            severity = violation.get('classification', 'Standard')
            if severity in violation_counts:
                violation_counts[severity] += 1
    
    return jsonify({
        "total_forms": len(summary),
        "classifications": classifications,
        "violation_counts": violation_counts
    })

@app.route('/api/download-pdf/<identifier>')
def download_pdf(identifier):
    """API endpoint to download PDF file"""
    from flask import send_file
    import os
    
    # Construct PDF filename from identifier (e.g., FDA_189622 -> FDA_189622.pdf)
    pdf_filename = f"{identifier}.pdf"
    pdfs_folder = os.environ.get('DOWNLOADED_PDFS_DIR', './downloaded_pdfs')
    pdf_path = os.path.join(pdfs_folder, pdf_filename)
    
    if os.path.exists(pdf_path):
        return send_file(pdf_path, as_attachment=True, download_name=pdf_filename)
    else:
        return jsonify({"error": "PDF file not found"}), 404

if __name__ == '__main__':
    # Create templates directory if it doesn't exist
    os.makedirs('templates', exist_ok=True)
    os.makedirs('static', exist_ok=True)
    
    app.run(debug=True, port=5000)

