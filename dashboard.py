"""
Dashboard for displaying FDA 483 Form Analysis Results
Web-based dashboard using Flask
"""

from flask import Flask, render_template, jsonify, request
import json
import os
import re
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime
import pandas as pd
from openai import OpenAI

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

def generate_violation_analysis_answer(detail_data: Dict, firm_name: str) -> str:
    """Generate direct answer about violations from JSON data"""
    # Get violations from violations_by_severity structure
    violations_by_severity = detail_data.get('violations_by_severity', {})
    
    # Flatten all violations to get total count
    all_violations = []
    for severity, violations in violations_by_severity.items():
        all_violations.extend(violations)
    
    if not all_violations:
        return f"**{firm_name}** has no violations recorded in the inspection data."
    
    answer = f"**Violation Analysis for {firm_name}:**\n\n"
    answer += f"**Total Violations:** {len(all_violations)}\n\n"
    
    # Critical violations
    critical = violations_by_severity.get("Critical", [])
    if critical:
        answer += f"**Critical Violations ({len(critical)}):**\n"
        for v in critical:
            answer += f"- **Observation {v.get('observation_number', 'N/A')}**: {v.get('rationale', 'N/A')}\n"
            answer += f"  - Violation Code: {v.get('violation_code', 'N/A')}\n"
            answer += f"  - Risk Level: {v.get('risk_level', 'N/A')}\n"
            if v.get('is_repeat'):
                answer += f"  - ⚠️ **Repeat Violation**\n"
            answer += f"  - Action Required: {v.get('action_required', 'N/A')}\n\n"
    
    # Significant violations
    significant = violations_by_severity.get("Significant", [])
    if significant:
        answer += f"**Significant Violations ({len(significant)}):**\n"
        for v in significant:
            answer += f"- **Observation {v.get('observation_number', 'N/A')}**: {v.get('rationale', 'N/A')}\n"
            answer += f"  - Violation Code: {v.get('violation_code', 'N/A')}\n"
            answer += f"  - Risk Level: {v.get('risk_level', 'N/A')}\n"
            if v.get('is_repeat'):
                answer += f"  - ⚠️ **Repeat Violation**\n"
            answer += f"  - Action Required: {v.get('action_required', 'N/A')}\n\n"
    
    # Standard violations
    standard = violations_by_severity.get("Standard", [])
    if standard:
        answer += f"**Standard Violations ({len(standard)}):**\n"
        for v in standard:
            answer += f"- **Observation {v.get('observation_number', 'N/A')}**: {v.get('rationale', 'N/A')}\n"
            answer += f"  - Violation Code: {v.get('violation_code', 'N/A')}\n"
            answer += f"  - Action Required: {v.get('action_required', 'N/A')}\n\n"
    
    return answer

def generate_followup_actions_answer(detail_data: Dict, firm_name: str) -> str:
    """Generate direct answer about follow-up actions from JSON data"""
    follow_up = detail_data.get('follow_up_actions', {})
    if not follow_up:
        return f"**{firm_name}** has no follow-up actions specified in the inspection data."
    
    answer = f"**Follow-Up Actions for {firm_name}:**\n\n"
    
    # Immediate actions
    immediate = follow_up.get('immediate', [])
    if immediate:
        answer += f"**Immediate Actions (Within 15 Days):**\n"
        for i, action in enumerate(immediate, 1):
            answer += f"{i}. {action}\n"
        answer += "\n"
    
    # Short-term actions
    short_term = follow_up.get('short_term', [])
    if short_term:
        answer += f"**Short-Term Actions (30-60 Days):**\n"
        for i, action in enumerate(short_term, 1):
            answer += f"{i}. {action}\n"
        answer += "\n"
    
    # Long-term actions
    long_term = follow_up.get('long_term', [])
    if long_term:
        answer += f"**Long-Term Actions (6-12 Months):**\n"
        for i, action in enumerate(long_term, 1):
            answer += f"{i}. {action}\n"
        answer += "\n"
    
    if not immediate and not short_term and not long_term:
        answer = f"**{firm_name}** has no follow-up actions specified in the inspection data."
    
    return answer

def generate_firm_basic_details_answer(firm_match: Dict, detail_data: Dict) -> str:
    """Generate answer with basic firm details (FEI, publish date, etc.)"""
    firm_name = firm_match.get('firm', 'Unknown')
    fei = firm_match.get('fei', 'N/A')
    publish_date = firm_match.get('publish_date', '')
    classification = firm_match.get('overall_classification', 'N/A')
    violation_count = firm_match.get('violation_count', 0)
    compliance_programs = firm_match.get('relevant_compliance_programs', [])
    
    answer = f"**Basic Details for {firm_name}:**\n\n"
    answer += f"- **FEI Number:** {fei}\n"
    
    if publish_date:
        # Format date nicely
        try:
            date_obj = datetime.strptime(publish_date.split()[0], '%Y-%m-%d')
            formatted_date = date_obj.strftime('%B %d, %Y')
            answer += f"- **Publish Date:** {formatted_date}\n"
        except:
            answer += f"- **Publish Date:** {publish_date}\n"
    else:
        answer += f"- **Publish Date:** Not available\n"
    
    answer += f"- **Classification:** {classification}"
    if classification == 'OAI':
        answer += " (Official Action Indicated)"
    elif classification == 'VAI':
        answer += " (Voluntary Action Indicated)"
    elif classification == 'NAI':
        answer += " (No Action Indicated)"
    answer += "\n"
    
    answer += f"- **Total Violations:** {violation_count}\n"
    
    if compliance_programs:
        answer += f"- **Compliance Programs:** {', '.join(compliance_programs)}\n"
    
    # Add processed date if available
    if detail_data and detail_data.get('metadata'):
        processed_date = detail_data.get('metadata', {}).get('processed_date', '')
        if processed_date:
            try:
                date_obj = datetime.fromisoformat(processed_date.replace('Z', '+00:00'))
                formatted_date = date_obj.strftime('%B %d, %Y')
                answer += f"- **Processed Date:** {formatted_date}\n"
            except:
                pass
    
    return answer

def generate_firms_by_date_range_answer(start_date: datetime, end_date: datetime, include_details: bool = True) -> str:
    """Generate answer with firms published within a date range"""
    summary_data = dashboard.get_summary_data()
    
    # Filter firms within date range
    matching_firms = []
    for item in summary_data:
        publish_date = item.get('publish_date', '')
        if publish_date:
            try:
                # Parse date (format: YYYY-MM-DD or YYYY-MM-DD HH:MM:SS)
                date_str = publish_date.split()[0]  # Get date part only
                item_date = datetime.strptime(date_str, '%Y-%m-%d')
                
                # Check if date is within range (inclusive)
                if start_date.date() <= item_date.date() <= end_date.date():
                    matching_firms.append(item)
            except Exception as e:
                # Skip if date parsing fails
                continue
    
    if not matching_firms:
        start_str = start_date.strftime('%B %d, %Y')
        end_str = end_date.strftime('%B %d, %Y')
        return f"No firms found published between **{start_str}** and **{end_str}**."
    
    # Sort by publish date (newest first)
    matching_firms.sort(key=lambda x: (
        datetime.strptime(x.get('publish_date', '').split()[0], '%Y-%m-%d') 
        if x.get('publish_date', '') else datetime.min
    ), reverse=True)
    
    start_str = start_date.strftime('%B %d, %Y')
    end_str = end_date.strftime('%B %d, %Y')
    answer = f"**Forms Published Between {start_str} and {end_str} ({len(matching_firms)} total):**\n\n"
    
    for i, firm in enumerate(matching_firms, 1):
        firm_name = firm.get('firm', 'Unknown')
        fei = firm.get('fei', 'N/A')
        classification = firm.get('overall_classification', 'N/A')
        violation_count = firm.get('violation_count', 0)
        publish_date = firm.get('publish_date', '')
        compliance_programs = firm.get('relevant_compliance_programs', [])
        
        answer += f"{i}. **{firm_name}**"
        if fei != 'N/A':
            answer += f" (FEI: {fei})"
        answer += "\n"
        
        if publish_date:
            try:
                date_obj = datetime.strptime(publish_date.split()[0], '%Y-%m-%d')
                formatted_date = date_obj.strftime('%B %d, %Y')
                answer += f"   - **Published:** {formatted_date}\n"
            except:
                answer += f"   - **Published:** {publish_date}\n"
        
        answer += f"   - **Classification:** {classification}"
        if classification == 'OAI':
            answer += " (Official Action Indicated)"
        elif classification == 'VAI':
            answer += " (Voluntary Action Indicated)"
        elif classification == 'NAI':
            answer += " (No Action Indicated)"
        answer += "\n"
        
        answer += f"   - **Violations:** {violation_count}\n"
        
        if compliance_programs:
            answer += f"   - **Compliance Programs:** {', '.join(compliance_programs)}\n"
        
        # Include additional details if requested
        if include_details:
            detail_data = dashboard.get_detail_data(firm.get('id'))
            if detail_data:
                justification = detail_data.get('classification_justification', '')
                if justification:
                    # Truncate if too long
                    if len(justification) > 200:
                        justification = justification[:200] + "..."
                    answer += f"   - **Justification:** {justification}\n"
        
        answer += "\n"
    
    return answer

def generate_recently_published_firms_answer(limit: int = 10, include_details: bool = True) -> str:
    """Generate answer with details of recently published firms"""
    summary_data = dashboard.get_summary_data()
    
    # Filter firms with publish dates and sort by date (newest first)
    firms_with_dates = []
    for item in summary_data:
        publish_date = item.get('publish_date', '')
        if publish_date:
            try:
                date_obj = datetime.strptime(publish_date.split()[0], '%Y-%m-%d')
                firms_with_dates.append((date_obj, item))
            except:
                pass
    
    if not firms_with_dates:
        return "No firms with publish dates found in the database."
    
    # Sort by date (newest first)
    firms_with_dates.sort(key=lambda x: x[0], reverse=True)
    
    # Get the most recent firms
    recent_firms = [item for _, item in firms_with_dates[:limit]]
    
    answer = f"**Recently Published Firms (Most Recent {len(recent_firms)}):**\n\n"
    
    for i, firm in enumerate(recent_firms, 1):
        firm_name = firm.get('firm', 'Unknown')
        fei = firm.get('fei', 'N/A')
        classification = firm.get('overall_classification', 'N/A')
        violation_count = firm.get('violation_count', 0)
        publish_date = firm.get('publish_date', '')
        compliance_programs = firm.get('relevant_compliance_programs', [])
        
        answer += f"{i}. **{firm_name}**"
        if fei != 'N/A':
            answer += f" (FEI: {fei})"
        answer += "\n"
        
        if publish_date:
            try:
                date_obj = datetime.strptime(publish_date.split()[0], '%Y-%m-%d')
                formatted_date = date_obj.strftime('%B %d, %Y')
                answer += f"   - **Published:** {formatted_date}\n"
            except:
                answer += f"   - **Published:** {publish_date}\n"
        
        answer += f"   - **Classification:** {classification}"
        if classification == 'OAI':
            answer += " (Official Action Indicated)"
        elif classification == 'VAI':
            answer += " (Voluntary Action Indicated)"
        elif classification == 'NAI':
            answer += " (No Action Indicated)"
        answer += "\n"
        
        answer += f"   - **Violations:** {violation_count}\n"
        
        if compliance_programs:
            answer += f"   - **Compliance Programs:** {', '.join(compliance_programs)}\n"
        
        # Include additional details if requested
        if include_details:
            detail_data = dashboard.get_detail_data(firm.get('id'))
            if detail_data:
                justification = detail_data.get('classification_justification', '')
                if justification:
                    # Truncate if too long
                    if len(justification) > 200:
                        justification = justification[:200] + "..."
                    answer += f"   - **Justification:** {justification}\n"
        
        answer += "\n"
    
    return answer

def generate_firms_by_classification_answer(classification: str) -> str:
    """Generate answer listing all firms with a specific classification"""
    summary_data = dashboard.get_summary_data()
    
    # Normalize classification
    classification_upper = classification.upper()
    if classification_upper not in ['OAI', 'VAI', 'NAI']:
        return f"Invalid classification. Please use OAI, VAI, or NAI."
    
    # Filter firms by classification
    matching_firms = [item for item in summary_data if item.get('overall_classification', '').upper() == classification_upper]
    
    if not matching_firms:
        return f"No firms found with classification **{classification_upper}**."
    
    answer = f"**Firms with {classification_upper} Classification ({len(matching_firms)} total):**\n\n"
    
    # Sort by firm name for easier reading
    matching_firms.sort(key=lambda x: x.get('firm', '').lower())
    
    for i, firm in enumerate(matching_firms, 1):
        firm_name = firm.get('firm', 'Unknown')
        fei = firm.get('fei', 'N/A')
        violation_count = firm.get('violation_count', 0)
        publish_date = firm.get('publish_date', '')
        
        answer += f"{i}. **{firm_name}**"
        if fei != 'N/A':
            answer += f" (FEI: {fei})"
        answer += f"\n"
        answer += f"   - Violations: {violation_count}\n"
        if publish_date:
            try:
                date_obj = datetime.strptime(publish_date.split()[0], '%Y-%m-%d')
                formatted_date = date_obj.strftime('%Y-%m-%d')
                answer += f"   - Published: {formatted_date}\n"
            except:
                answer += f"   - Published: {publish_date}\n"
        answer += "\n"
    
    return answer

def generate_risk_prioritization_answer(detail_data: Dict, firm_name: str) -> str:
    """Generate direct answer about risk prioritization from JSON data"""
    risk = detail_data.get('risk_prioritization', {})
    if not risk:
        return f"**{firm_name}** has no risk prioritization data in the inspection records."
    
    answer = f"**Risk Prioritization for {firm_name}:**\n\n"
    
    # High priority elements
    high_priority = risk.get('high_priority_elements', [])
    if high_priority:
        answer += f"**High Priority Elements:**\n"
        for i, element in enumerate(high_priority, 1):
            answer += f"{i}. {element}\n"
        answer += "\n"
    
    # Regulatory meeting topics
    meeting_topics = risk.get('regulatory_meeting_topics', [])
    if meeting_topics:
        answer += f"**Regulatory Meeting Topics:**\n"
        for i, topic in enumerate(meeting_topics, 1):
            answer += f"{i}. {topic}\n"
        answer += "\n"
    
    if not high_priority and not meeting_topics:
        answer = f"**{firm_name}** has no risk prioritization data in the inspection records."
    
    return answer

def search_firm_by_name(firm_name: str) -> Optional[Dict]:
    """Search for a firm by name in the results cache (case-insensitive partial match)"""
    firm_name_lower = firm_name.lower().strip()
    
    # Get all summary data
    summary_data = dashboard.get_summary_data()
    
    # Try exact match first
    for item in summary_data:
        if item.get('firm', '').lower() == firm_name_lower:
            return item
    
    # Try partial match
    for item in summary_data:
        firm = item.get('firm', '').lower()
        if firm_name_lower in firm or firm in firm_name_lower:
            return item
    
    # Try matching key words (e.g., "Alvotech HF" should match "Alvotech HF Firm")
    firm_keywords = [word for word in firm_name_lower.split() if len(word) > 3]
    for item in summary_data:
        firm = item.get('firm', '').lower()
        if all(keyword in firm for keyword in firm_keywords):
            return item
    
    return None

@app.route('/api/chatbot', methods=['POST'])
def chatbot():
    """API endpoint for chatbot questions about FDA 483 inspections"""
    try:
        data = request.get_json()
        question = data.get('question', '').strip()
        identifier = data.get('identifier', None)  # Optional: specific inspection ID
        
        if not question:
            return jsonify({"error": "Question is required"}), 400
        
        question_lower = question.lower()
        
        # Check for date range queries FIRST (e.g., "forms published between 10/30/2025 and 11/05/2025")
        date_range_patterns = [
            r'published between (.+?) and (.+?)(?:\?|$)',
            r'forms? published between (.+?) and (.+?)(?:\?|$)',
            r'firms? published between (.+?) and (.+?)(?:\?|$)',
            r'between (.+?) and (.+?)(?:\?|$)',
            r'from (.+?) to (.+?)(?:\?|$)',
        ]
        
        for pattern in date_range_patterns:
            match = re.search(pattern, question_lower, re.IGNORECASE)
            if match:
                date1_str = match.group(1).strip()
                date2_str = match.group(2).strip()
                
                # Clean up date strings (remove common words)
                date1_str = re.sub(r'\b(and|the|on|date|dates)\b', '', date1_str, flags=re.IGNORECASE).strip()
                date2_str = re.sub(r'\b(and|the|on|date|dates)\b', '', date2_str, flags=re.IGNORECASE).strip()
                
                # Try to parse dates in various formats
                start_date = None
                end_date = None
                
                date_formats = [
                    '%m/%d/%Y',  # MM/DD/YYYY
                    '%m-%d-%Y',  # MM-DD-YYYY
                    '%Y-%m-%d',  # YYYY-MM-DD
                    '%m/%d/%y',  # MM/DD/YY
                    '%Y/%m/%d',  # YYYY/MM/DD
                    '%d/%m/%Y',  # DD/MM/YYYY
                ]
                
                for fmt in date_formats:
                    try:
                        start_date = datetime.strptime(date1_str, fmt)
                        break
                    except:
                        continue
                
                for fmt in date_formats:
                    try:
                        end_date = datetime.strptime(date2_str, fmt)
                        break
                    except:
                        continue
                
                if start_date and end_date:
                    # Ensure start_date is before end_date
                    if start_date > end_date:
                        start_date, end_date = end_date, start_date
                    
                    include_details = 'detail' in question_lower
                    answer = generate_firms_by_date_range_answer(start_date, end_date, include_details=include_details)
                    return jsonify({
                        "answer": answer,
                        "identifier": None,
                        "direct_answer": True
                    })
        
        # Check for questions about recently published firms FIRST (before firm name extraction)
        # This handles questions like "Give the first 3 details of the firms that are published recently"
        recent_keywords = [
            'recently published', 
            'published recently', 
            'recent published',  # Handle "recent published" without "ly"
            'recent published dates',
            'recent published firms',
            'latest published', 
            'newest firms', 
            'most recent',
            'recent firms',
            'published dates'
        ]
        if any(keyword in question_lower for keyword in recent_keywords):
            # Check if "details" is mentioned
            include_details = 'detail' in question_lower
            
            # Try multiple patterns to extract number limit
            limit = 10  # default
            
            # Pattern 1: "first 3", "first 5", etc.
            first_match = re.search(r'first\s+(\d+)', question_lower, re.IGNORECASE)
            if first_match:
                limit = int(first_match.group(1))
            else:
                # Pattern 2: "5 recent", "3 recently published", "5 firms", etc.
                # This catches "give the 5 recent published dates firms"
                limit_match = re.search(r'(\d+)\s*(?:recent|recently published|recent published|latest|newest|firms?|details?|published)', question_lower, re.IGNORECASE)
                if limit_match:
                    limit = int(limit_match.group(1))
                else:
                    # Pattern 3: "top 3", "top 5", etc.
                    top_match = re.search(r'top\s+(\d+)', question_lower, re.IGNORECASE)
                    if top_match:
                        limit = int(top_match.group(1))
                    else:
                        # Pattern 4: "the 5", "the 3", etc. (catches "give the 5 recent...")
                        the_match = re.search(r'the\s+(\d+)', question_lower, re.IGNORECASE)
                        if the_match:
                            limit = int(the_match.group(1))
            
            answer = generate_recently_published_firms_answer(limit, include_details=include_details)
            return jsonify({
                "answer": answer,
                "identifier": None,
                "direct_answer": True
            })
        
        # Check if question is asking about a specific firm
        # Look for firm name patterns in the question
        firm_match = None
        
        # First, try to extract firm name from common question patterns
        potential_firm_names = []
        patterns = [
            r'which classification does (.+?) come under',
            r'what classification is (.+?)',
            r'classification of (.+?)',
            r'(.+?) classification',
            r'(.+?) firm',
            r'firm (.+?)',
            r'tell me about (.+?)(?:\?|$)',
            r'what is (.+?)(?:\?|$)',
            r'who is (.+?)(?:\?|$)',
            r'information about (.+?)(?:\?|$)',
            r'details about (.+?)(?:\?|$)',
            r'fei (?:of|for) (.+?)(?:\?|$)',
            r'publish date (?:of|for) (.+?)(?:\?|$)',
            r'violations (?:of|for) (.+?)(?:\?|$)',
            r'follow-up actions (?:of|for) (.+?)(?:\?|$)',
        ]
        
        for pattern in patterns:
            matches = re.finditer(pattern, question_lower, re.IGNORECASE)
            for match in matches:
                extracted = match.group(1).strip()
                # Clean up common words
                extracted = re.sub(r'\b(firm|company|facility|establishment|come|under|does|is|the|a|an)\b', '', extracted, flags=re.IGNORECASE).strip()
                if extracted and len(extracted) > 2:
                    potential_firm_names.append(extracted)
        
        # Search strategy: try extracted names first, then search all firms
        if potential_firm_names:
            for potential in potential_firm_names:
                firm_match = search_firm_by_name(potential)
                if firm_match:
                    break
        
        # If no match yet, search all firm names in database against question
        if not firm_match:
            summary_data = dashboard.get_summary_data()
            
            # Search strategy: exact match > partial match > keyword match
            for item in summary_data:
                firm_name = item.get('firm', '').lower().strip()
                if not firm_name or firm_name == 'unknown':
                    continue
                
                # Check exact match
                if firm_name in question_lower:
                    firm_match = item
                    break
                
                # Check keyword match (all significant words from firm name appear in question)
                firm_words = [w for w in firm_name.split() if len(w) > 3]
                if firm_words and all(word in question_lower for word in firm_words):
                    firm_match = item
                    break
        
        # Check for questions about recently published firms
        recent_patterns = [
            r'recently published',
            r'recently published firms',
            r'firms (?:that are|which are) (?:recently )?published (?:recently)?',
            r'firms (?:that are|which are) published recently',
            r'give (?:me )?details? (?:of|about) firms? (?:that are|which are) (?:recently )?published',
            r'latest published firms?',
            r'newest firms?',
            r'most recent firms?',
            r'recent firms?',
            r'firms? published (?:recently|latest|newest)',
            r'published (?:recently|latest)',
        ]
        
        for pattern in recent_patterns:
            if re.search(pattern, question_lower, re.IGNORECASE):
                # Check if "details" is mentioned
                include_details = 'detail' in question_lower
                
                # Try multiple patterns to extract number limit
                limit = 10  # default
                
                # Pattern 1: "first 3", "first 5", etc.
                first_match = re.search(r'first\s+(\d+)', question_lower, re.IGNORECASE)
                if first_match:
                    limit = int(first_match.group(1))
                else:
                    # Pattern 2: "3 recently published", "5 firms", etc.
                    limit_match = re.search(r'(\d+)\s*(?:recently published|recent|latest|newest|firms?|details?)', question_lower, re.IGNORECASE)
                    if limit_match:
                        limit = int(limit_match.group(1))
                    else:
                        # Pattern 3: "top 3", "top 5", etc.
                        top_match = re.search(r'top\s+(\d+)', question_lower, re.IGNORECASE)
                        if top_match:
                            limit = int(top_match.group(1))
                
                answer = generate_recently_published_firms_answer(limit, include_details=include_details)
                return jsonify({
                    "answer": answer,
                    "identifier": None,
                    "direct_answer": True
                })
        
        # Check for analytical questions that require analyzing ALL records
        # Questions about highest/most violations
        highest_violation_patterns = [
            r'which firm (?:has|have) (?:the )?(?:highest|most|maximum) violations?',
            r'which firm (?:has|have) (?:the )?most violations?',
            r'firm (?:with|having) (?:the )?(?:highest|most|maximum) violations?',
            r'(?:highest|most|maximum) violations?',
            r'top (?:firm|firms) (?:with|by) (?:violations?|violation count)',
        ]
        
        for pattern in highest_violation_patterns:
            if re.search(pattern, question_lower, re.IGNORECASE):
                summary_data = dashboard.get_summary_data()  # Get ALL records
                if not summary_data:
                    return jsonify({
                        "answer": "No inspection data available.",
                        "identifier": None,
                        "direct_answer": True
                    })
                
                # Sort by violation count (descending)
                sorted_firms = sorted(summary_data, key=lambda x: x.get('violation_count', 0), reverse=True)
                
                # Check if asking for top N
                top_match = re.search(r'top\s+(\d+)', question_lower, re.IGNORECASE)
                limit = int(top_match.group(1)) if top_match else 1
                
                answer = f"**Firm{'s' if limit > 1 else ''} with {'Highest' if limit == 1 else 'Most'} Violations:**\n\n"
                
                for i, firm in enumerate(sorted_firms[:limit], 1):
                    firm_name = firm.get('firm', 'Unknown')
                    fei = firm.get('fei', 'N/A')
                    violation_count = firm.get('violation_count', 0)
                    classification = firm.get('overall_classification', 'N/A')
                    publish_date = firm.get('publish_date', '')
                    
                    answer += f"{i}. **{firm_name}**"
                    if fei != 'N/A':
                        answer += f" (FEI: {fei})"
                    answer += f"\n   - **Violations:** {violation_count}\n"
                    answer += f"   - **Classification:** {classification}\n"
                    if publish_date:
                        try:
                            date_obj = datetime.strptime(publish_date.split()[0], '%Y-%m-%d')
                            formatted_date = date_obj.strftime('%Y-%m-%d')
                            answer += f"   - **Published:** {formatted_date}\n"
                        except:
                            pass
                    answer += "\n"
                
                return jsonify({
                    "answer": answer,
                    "identifier": None,
                    "direct_answer": True
                })
        
        # Questions about lowest/fewest violations
        lowest_violation_patterns = [
            r'which firm (?:has|have) (?:the )?(?:lowest|fewest|minimum) violations?',
            r'which firm (?:has|have) (?:the )?fewest violations?',
            r'firm (?:with|having) (?:the )?(?:lowest|fewest|minimum) violations?',
        ]
        
        for pattern in lowest_violation_patterns:
            if re.search(pattern, question_lower, re.IGNORECASE):
                summary_data = dashboard.get_summary_data()  # Get ALL records
                if not summary_data:
                    return jsonify({
                        "answer": "No inspection data available.",
                        "identifier": None,
                        "direct_answer": True
                    })
                
                # Sort by violation count (ascending)
                sorted_firms = sorted(summary_data, key=lambda x: x.get('violation_count', 0))
                
                answer = "**Firm with Fewest Violations:**\n\n"
                firm = sorted_firms[0]
                firm_name = firm.get('firm', 'Unknown')
                fei = firm.get('fei', 'N/A')
                violation_count = firm.get('violation_count', 0)
                classification = firm.get('overall_classification', 'N/A')
                publish_date = firm.get('publish_date', '')
                
                answer += f"**{firm_name}**"
                if fei != 'N/A':
                    answer += f" (FEI: {fei})"
                answer += f"\n   - **Violations:** {violation_count}\n"
                answer += f"   - **Classification:** {classification}\n"
                if publish_date:
                    try:
                        date_obj = datetime.strptime(publish_date.split()[0], '%Y-%m-%d')
                        formatted_date = date_obj.strftime('%Y-%m-%d')
                        answer += f"   - **Published:** {formatted_date}\n"
                    except:
                        pass
                
                return jsonify({
                    "answer": answer,
                    "identifier": None,
                    "direct_answer": True
                })
        
        # Questions about average violations
        average_patterns = [
            r'what (?:is|are) the (?:average|mean) violations?',
            r'average (?:number of )?violations?',
            r'mean violations?',
        ]
        
        for pattern in average_patterns:
            if re.search(pattern, question_lower, re.IGNORECASE):
                summary_data = dashboard.get_summary_data()  # Get ALL records
                if not summary_data:
                    return jsonify({
                        "answer": "No inspection data available.",
                        "identifier": None,
                        "direct_answer": True
                    })
                
                total_violations = sum(item.get('violation_count', 0) for item in summary_data)
                avg_violations = total_violations / len(summary_data) if summary_data else 0
                
                answer = f"**Average Violations Across All Firms:**\n\n"
                answer += f"Total Firms: {len(summary_data)}\n"
                answer += f"Total Violations: {total_violations}\n"
                answer += f"Average Violations per Firm: {avg_violations:.2f}\n"
                
                return jsonify({
                    "answer": answer,
                    "identifier": None,
                    "direct_answer": True
                })
        
        # Check for aggregate questions (e.g., "how many firms are OAI?")
        aggregate_patterns = [
            r'how many firms (?:are|have|classified as) (oai|vai|nai)',
            r'what is the (?:total )?number of (oai|vai|nai) firms',
            r'count of (oai|vai|nai) firms',
            r'total (oai|vai|nai) firms',
        ]
        
        for pattern in aggregate_patterns:
            match = re.search(pattern, question_lower, re.IGNORECASE)
            if match:
                classification = match.group(1).upper()
                summary_data = dashboard.get_summary_data()
                matching_firms = [item for item in summary_data if item.get('overall_classification', '').upper() == classification]
                count = len(matching_firms)
                answer = f"There are **{count}** firms with **{classification}** classification."
                if count > 0:
                    answer += f"\n\nWould you like to see the list of these firms?"
                return jsonify({
                    "answer": answer,
                    "identifier": None,
                    "direct_answer": True
                })
        
        # Check for questions about firms by classification (e.g., "which firms are OAI?")
        classification_questions = [
            r'which firms (?:are|have|come under|classified as) (oai|vai|nai)',
            r'list (?:all )?firms (?:with|that have|classified as) (oai|vai|nai)',
            r'show (?:me )?(?:all )?firms (?:with|that have|classified as) (oai|vai|nai)',
            r'what firms (?:are|have|classified as) (oai|vai|nai)',
            r'(oai|vai|nai) firms',
            r'firms (?:with|under) (oai|vai|nai)',
        ]
        
        for pattern in classification_questions:
            match = re.search(pattern, question_lower, re.IGNORECASE)
            if match:
                classification = match.group(1).upper()
                answer = generate_firms_by_classification_answer(classification)
                return jsonify({
                    "answer": answer,
                    "identifier": None,
                    "direct_answer": True
                })
        
        # If firm found, check what type of question it is and provide direct answer from JSON
        if firm_match:
            detail_data = dashboard.get_detail_data(firm_match.get('id'))
            firm_name = firm_match.get('firm', 'Unknown')
            
            if not detail_data:
                # Fall through to OpenAI if detail data not available
                pass
            else:
                # Check question type and provide direct answer from JSON
                answer_parts = []
                
                # Basic details questions (FEI, publish date, general info)
                # Check for specific questions about FEI or publish date first
                if any(keyword in question_lower for keyword in ['fei', 'facility establishment identifier']):
                    fei = firm_match.get('fei', 'N/A')
                    answer_parts.append(f"**FEI Number for {firm_name}:** {fei}\n")
                
                if any(keyword in question_lower for keyword in ['publish date', 'published', 'when was', 'date published']):
                    publish_date = firm_match.get('publish_date', '')
                    if publish_date:
                        try:
                            date_obj = datetime.strptime(publish_date.split()[0], '%Y-%m-%d')
                            formatted_date = date_obj.strftime('%B %d, %Y')
                            answer_parts.append(f"**Publish Date for {firm_name}:** {formatted_date}\n")
                        except:
                            answer_parts.append(f"**Publish Date for {firm_name}:** {publish_date}\n")
                    else:
                        answer_parts.append(f"**Publish Date for {firm_name}:** Not available\n")
                
                # General questions about the firm (tell me about, what is, etc.)
                if any(keyword in question_lower for keyword in ['tell me about', 'what is', 'who is', 'information about', 'details about', 'basic', 'general', 'overview']) or \
                   (not answer_parts and firm_match):  # If no specific question type matched, provide basic details
                    basic_answer = generate_firm_basic_details_answer(firm_match, detail_data)
                    answer_parts.append(basic_answer)
                
                # Classification questions
                if any(keyword in question_lower for keyword in ['classification', 'classify', 'class', 'oai', 'vai', 'nai']):
                    classification = firm_match.get('overall_classification', 'N/A')
                    fei = firm_match.get('fei', 'N/A')
                    violation_count = firm_match.get('violation_count', 0)
                    compliance_programs = firm_match.get('relevant_compliance_programs', [])
                    
                    answer_parts.append(f"**{firm_name}** (FEI: {fei}) has been classified as **{classification}**")
                    if classification == 'OAI':
                        answer_parts[-1] += " (Official Action Indicated)"
                    elif classification == 'VAI':
                        answer_parts[-1] += " (Voluntary Action Indicated)"
                    elif classification == 'NAI':
                        answer_parts[-1] += " (No Action Indicated)"
                    
                    answer_parts.append(f"\n\n**Details:**\n")
                    answer_parts.append(f"- Total Violations: {violation_count}\n")
                    if compliance_programs:
                        answer_parts.append(f"- Relevant Compliance Programs: {', '.join(compliance_programs)}\n")
                    
                    justification = detail_data.get('classification_justification', '')
                    if justification:
                        answer_parts.append(f"\n**Classification Justification:**\n{justification}\n")
                
                # Violation analysis questions
                if any(keyword in question_lower for keyword in ['violation', 'violations', 'observation', 'observations', 'violation analysis', 'what violations']):
                    violation_answer = generate_violation_analysis_answer(detail_data, firm_name)
                    answer_parts.append(violation_answer)
                
                # Follow-up actions questions (more specific to avoid matching "classification")
                if any(keyword in question_lower for keyword in ['follow-up', 'follow up', 'followup', 'follow-up action', 'follow up action', 'what actions', 'corrective action', 'regulatory action', 'immediate action', 'short-term action', 'long-term action']):
                    followup_answer = generate_followup_actions_answer(detail_data, firm_name)
                    answer_parts.append(followup_answer)
                
                # Risk prioritization questions
                if any(keyword in question_lower for keyword in ['risk', 'prioritization', 'priority', 'risk prioritization', 'high priority', 'regulatory meeting']):
                    risk_answer = generate_risk_prioritization_answer(detail_data, firm_name)
                    answer_parts.append(risk_answer)
                
                # If we have direct answers, return them
                if answer_parts:
                    combined_answer = "\n\n".join(answer_parts)
                    return jsonify({
                        "answer": combined_answer,
                        "identifier": firm_match.get('id'),
                        "direct_answer": True
                    })
        
        # If firm found but question is not specifically about classification, use it as context
        if firm_match and not identifier:
            identifier = firm_match.get('id')
        
        # Get OpenAI API key
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return jsonify({"error": "OpenAI API key not configured"}), 500
        
        client = OpenAI(api_key=api_key)
        
        # Build comprehensive context from ALL available dashboard data
        compliance_guide = build_compliance_guide_context()
        dashboard_context = build_comprehensive_dashboard_context()
        inspection_context = ""
        
        # If identifier provided, include specific inspection data
        if identifier and identifier in dashboard.results_cache:
            inspection_data = dashboard.get_detail_data(identifier)
            inspection_context = build_inspection_context(inspection_data)
        elif firm_match:
            # Use firm match data even if identifier wasn't explicitly provided
            inspection_data = dashboard.get_detail_data(firm_match.get('id'))
            inspection_context = build_inspection_context(inspection_data)
        
        # Create enhanced system prompt
        system_prompt = """You are an FDA compliance expert assistant with access to a comprehensive database of FDA Form 483 inspection results. 
You MUST answer ALL questions using ONLY the data provided in the context below. 

CRITICAL RULES:
1. ALWAYS use the actual data from the dashboard context provided - never say you don't have access to data
2. If data is available in the context, use it directly - do NOT give generic responses
3. For questions about specific firms, search the provided firm list and use their actual data
4. For statistical questions, calculate from the provided data - the dashboard context shows statistics for ALL records in the database
5. For analytical questions (e.g., "which firm has highest violations", "top firms by violations"), analyze ALL records mentioned in the statistics, not just the sample list shown
6. The dashboard context includes summary statistics calculated from ALL records in the database - use these for comprehensive analysis
7. For date range questions, filter the provided data by dates
8. If a firm is not found in the data, say so clearly but still provide general guidance
9. Always reference specific compliance program codes, classifications, and violation counts from the data
10. Be precise and factual - use exact numbers, dates, and classifications from the data
11. IMPORTANT: When asked about "highest", "most", "top", "lowest", or similar analytical questions, use the statistics provided which are calculated from ALL records in the database

You have access to:
- Complete statistics calculated from ALL records in the database (total firms, classification distribution, total violations, etc.)
- Sample list of firms (first 100 shown for context, but statistics cover ALL records)
- Detailed violation analysis for each inspection
- Follow-up actions and risk prioritization data
- FDA Compliance Program guidelines

Answer questions directly using this data. For analytical questions, use the comprehensive statistics provided which reflect ALL records."""
        
        # Check if firm was mentioned but not found
        firm_not_found_message = ""
        if any(keyword in question_lower for keyword in ['classification', 'classify', 'class']) and not firm_match:
            # Try to extract potential firm name from question
            patterns = [
                r'which classification does (.+?) come under',
                r'what classification is (.+?)',
                r'classification of (.+?)',
                r'(.+?) classification',
            ]
            potential_firm = None
            for pattern in patterns:
                match = re.search(pattern, question_lower, re.IGNORECASE)
                if match:
                    potential_firm = match.group(1).strip()
                    potential_firm = re.sub(r'\b(firm|company|facility|establishment)\b', '', potential_firm, flags=re.IGNORECASE).strip()
                    if potential_firm:
                        break
            
            if potential_firm:
                firm_match = search_firm_by_name(potential_firm)
                if firm_match:
                    # Found it! Give direct answer
                    classification = firm_match.get('overall_classification', 'N/A')
                    firm_name = firm_match.get('firm', 'Unknown')
                    fei = firm_match.get('fei', 'N/A')
                    violation_count = firm_match.get('violation_count', 0)
                    compliance_programs = firm_match.get('relevant_compliance_programs', [])
                    
                    answer = f"**{firm_name}** (FEI: {fei}) has been classified as **{classification}**"
                    if classification == 'OAI':
                        answer += " (Official Action Indicated)"
                    elif classification == 'VAI':
                        answer += " (Voluntary Action Indicated)"
                    elif classification == 'NAI':
                        answer += " (No Action Indicated)"
                    
                    answer += f".\n\n**Details:**\n"
                    answer += f"- Total Violations: {violation_count}\n"
                    if compliance_programs:
                        answer += f"- Relevant Compliance Programs: {', '.join(compliance_programs)}\n"
                    
                    detail_data = dashboard.get_detail_data(firm_match.get('id'))
                    if detail_data:
                        justification = detail_data.get('classification_justification', '')
                        if justification:
                            answer += f"\n**Classification Justification:**\n{justification}\n"
                    
                    return jsonify({
                        "answer": answer,
                        "identifier": firm_match.get('id'),
                        "direct_answer": True
                    })
                else:
                    firm_not_found_message = f"\n\nNote: I searched for '{potential_firm}' in the database but could not find any inspection records. The firm list in the context shows all available firms - please check the spelling or use a firm name from the list."
        
        user_prompt = f"""FDA Compliance Program Guide:
{compliance_guide}

{dashboard_context}

{inspection_context if inspection_context else ""}

{firm_not_found_message}

User Question: {question}

INSTRUCTIONS:
- Answer the question using ONLY the data provided above
- IMPORTANT: The dashboard context includes comprehensive statistics calculated from ALL records in the database
- For analytical questions (highest violations, top firms, averages, etc.), use the comprehensive statistics provided which reflect ALL records
- The firm list shown is a sample (first 100), but statistics cover ALL records - use statistics for analytical questions
- If the question asks about specific firms, search the firm list in the dashboard context
- If asking for statistics, use the comprehensive statistics provided which are calculated from ALL records
- If asking about dates, use the publish dates from the firm list
- If asking about classifications, use the actual classifications shown in the data
- Be specific and factual - use exact numbers, names, and dates from the data
- If data is available, use it - do NOT say you don't have access to real-time data
- Provide clear, direct answers based on the actual inspection data provided

Answer:"""
        
        # Call OpenAI
        response = client.chat.completions.create(
            model="gpt-4-turbo-preview",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.3,
            max_tokens=2000  # Increased for comprehensive answers using dashboard data
        )
        
        answer = response.choices[0].message.content
        
        return jsonify({
            "answer": answer,
            "identifier": identifier
        })
        
    except Exception as e:
        return jsonify({"error": f"Error processing question: {str(e)}"}), 500

def build_compliance_guide_context() -> str:
    """Build compliance guide context from FDA Compliance Programs"""
    from fda_483_processor import FDA483Processor
    
    programs = FDA483Processor.COMPLIANCE_PROGRAMS
    classifications = FDA483Processor.CLASSIFICATIONS
    violation_levels = FDA483Processor.VIOLATION_LEVELS
    
    context = "FDA Compliance Program Guide:\n\n"
    context += "Classification Categories:\n"
    for code, desc in classifications.items():
        context += f"- {code}: {desc}\n"
    
    context += "\nViolation Severity Levels:\n"
    for level, desc in violation_levels.items():
        context += f"- {level}: {desc}\n"
    
    context += "\nFDA Compliance Programs:\n"
    for code, desc in programs.items():
        context += f"- {code}: {desc}\n"
    
    context += """
    
Classification Guidelines:
- OAI (Official Action Indicated): Assigned when violations are serious enough to warrant regulatory action. Typically involves critical violations, repeat violations, systemic failures, or patient safety risks. Examples: sterile product contamination, inadequate failure investigations, repeat violations from previous inspections.
- VAI (Voluntary Action Indicated): Assigned when violations are significant but the firm can address them voluntarily. The firm should take corrective action, but immediate regulatory action is not required.
- NAI (No Action Indicated): Assigned when no significant violations are found or only minor issues are present that don't require regulatory action.

Violation Analysis:
- Critical Violations: Immediate action required. Examples include sterile product contamination, failure investigations that are inadequate in scope, direct contamination risks during sterile processing, and violations that pose immediate patient safety risks.
- Significant Violations: Action required but not immediately critical. Examples include environmental monitoring deficiencies, trend investigation failures, quality system deficiencies, and inadequate corrective actions.
- Standard Violations: Documentation and procedural issues. Examples include laboratory documentation deficiencies, minor cGMP violations, and procedural non-compliance that doesn't pose immediate risk.

Follow-Up Actions:
- Immediate Actions (15 days): Regulatory meetings, response letters, product assessments, potential recall evaluations.
- Short-Term Actions (30-60 days): Warning letters, enhanced surveillance, import alert considerations, corrective action plan reviews.
- Long-Term Actions (6-12 months): Follow-up inspections, compliance verification, escalation assessments if violations persist.

Risk Prioritization Factors:
- High Priority: Sterile product contamination, repeat violations, investigation inadequacies, patient safety risks.
- Regulatory Meeting Topics: Comprehensive investigations, environmental monitoring program redesign, personnel training verification, quality system effectiveness assessment.
"""
    
    return context

def build_comprehensive_dashboard_context() -> str:
    """Build comprehensive context from all available dashboard data"""
    summary_data = dashboard.get_summary_data()
    
    if not summary_data:
        return "No inspection data is currently available in the dashboard."
    
    context = f"**COMPREHENSIVE DASHBOARD DATA (Total: {len(summary_data)} inspections):**\n\n"
    
    # Statistics
    classifications = {}
    total_violations = 0
    firms_by_program = {}
    date_range = {'earliest': None, 'latest': None}
    
    for item in summary_data:
        # Classification counts
        classification = item.get('overall_classification', 'N/A')
        classifications[classification] = classifications.get(classification, 0) + 1
        
        # Violation counts
        total_violations += item.get('violation_count', 0)
        
        # Compliance programs
        programs = item.get('relevant_compliance_programs', [])
        for program in programs:
            if program not in firms_by_program:
                firms_by_program[program] = []
            firms_by_program[program].append(item.get('firm', 'Unknown'))
        
        # Date range
        publish_date = item.get('publish_date', '')
        if publish_date:
            try:
                date_obj = datetime.strptime(publish_date.split()[0], '%Y-%m-%d')
                if date_range['earliest'] is None or date_obj < date_range['earliest']:
                    date_range['earliest'] = date_obj
                if date_range['latest'] is None or date_obj > date_range['latest']:
                    date_range['latest'] = date_obj
            except:
                pass
    
    context += f"**Classification Distribution:**\n"
    for cls, count in classifications.items():
        context += f"- {cls}: {count} firms\n"
    
    context += f"\n**Total Violations:** {total_violations}\n"
    
    if date_range['earliest'] and date_range['latest']:
        context += f"\n**Date Range:** {date_range['earliest'].strftime('%B %d, %Y')} to {date_range['latest'].strftime('%B %d, %Y')}\n"
    
    context += f"\n**Compliance Programs Coverage:**\n"
    for program, firms in firms_by_program.items():
        context += f"- {program}: {len(set(firms))} unique firms\n"
    
    # Add comprehensive statistics for analytical questions
    context += f"\n**Comprehensive Statistics (Based on ALL {len(summary_data)} Records):**\n"
    context += f"- Total Firms: {len(summary_data)}\n"
    context += f"- Total Violations: {total_violations}\n"
    context += f"- Average Violations per Firm: {total_violations / len(summary_data) if summary_data else 0:.2f}\n"
    
    # Find firms with highest and lowest violations
    if summary_data:
        sorted_by_violations = sorted(summary_data, key=lambda x: x.get('violation_count', 0), reverse=True)
        highest = sorted_by_violations[0]
        lowest = sorted_by_violations[-1]
        context += f"- Firm with Most Violations: {highest.get('firm', 'Unknown')} ({highest.get('violation_count', 0)} violations)\n"
        context += f"- Firm with Fewest Violations: {lowest.get('firm', 'Unknown')} ({lowest.get('violation_count', 0)} violations)\n"
    
    # List all firms with key information (limit to 100 for context size, but provide summary)
    context += f"\n**Sample Firms List (showing first 100 of {len(summary_data)} total firms):**\n"
    context += f"NOTE: The statistics above are calculated from ALL {len(summary_data)} records in the database.\n"
    context += f"For analytical questions (highest violations, top firms, etc.), use the comprehensive statistics provided above.\n\n"
    for i, item in enumerate(summary_data[:100], 1):  # Limit to first 100 for context size
        firm_name = item.get('firm', 'Unknown')
        fei = item.get('fei', 'N/A')
        classification = item.get('overall_classification', 'N/A')
        violation_count = item.get('violation_count', 0)
        publish_date = item.get('publish_date', '')
        
        context += f"{i}. {firm_name}"
        if fei != 'N/A':
            context += f" (FEI: {fei})"
        context += f" - {classification}, {violation_count} violations"
        if publish_date:
            try:
                date_obj = datetime.strptime(publish_date.split()[0], '%Y-%m-%d')
                context += f", Published: {date_obj.strftime('%Y-%m-%d')}"
            except:
                pass
        context += "\n"
    
    if len(summary_data) > 100:
        context += f"\n... and {len(summary_data) - 100} more firms. For specific firm details, ask about the firm by name.\n"
    
    return context

def build_inspection_context(inspection_data: Dict) -> str:
    """Build context from specific inspection data"""
    if not inspection_data:
        return ""
    
    context = f"\nSpecific Inspection Data:\n"
    context += f"Firm: {inspection_data.get('metadata', {}).get('firm', 'Unknown')}\n"
    context += f"FEI: {inspection_data.get('metadata', {}).get('fei', 'N/A')}\n"
    context += f"Overall Classification: {inspection_data.get('overall_classification', 'N/A')}\n"
    context += f"Classification Justification: {inspection_data.get('classification_justification', 'N/A')}\n"
    
    compliance_programs = inspection_data.get('relevant_compliance_programs', [])
    if compliance_programs:
        context += f"Relevant Compliance Programs: {', '.join(compliance_programs)}\n"
    
    # Add violations summary
    violations_by_severity = inspection_data.get('violations_by_severity', {})
    context += "\nViolations Summary:\n"
    for severity, violations in violations_by_severity.items():
        if violations:
            context += f"- {severity}: {len(violations)} violation(s)\n"
            for v in violations[:3]:  # Show first 3
                context += f"  * Observation {v.get('observation_number', 'N/A')}: {v.get('rationale', 'N/A')[:100]}...\n"
    
    # Add follow-up actions
    follow_up = inspection_data.get('follow_up_actions', {})
    if follow_up:
        context += "\nFollow-Up Actions:\n"
        if follow_up.get('immediate'):
            context += f"- Immediate: {', '.join(follow_up['immediate'][:3])}\n"
        if follow_up.get('short_term'):
            context += f"- Short-Term: {', '.join(follow_up['short_term'][:3])}\n"
        if follow_up.get('long_term'):
            context += f"- Long-Term: {', '.join(follow_up['long_term'][:3])}\n"
    
    # Add risk prioritization
    risk = inspection_data.get('risk_prioritization', {})
    if risk:
        context += "\nRisk Prioritization:\n"
        if risk.get('high_priority_elements'):
            context += f"- High Priority: {', '.join(risk['high_priority_elements'][:5])}\n"
        if risk.get('regulatory_meeting_topics'):
            context += f"- Regulatory Meeting Topics: {', '.join(risk['regulatory_meeting_topics'][:5])}\n"
    
    return context

if __name__ == '__main__':
    # Create templates directory if it doesn't exist
    os.makedirs('templates', exist_ok=True)
    os.makedirs('static', exist_ok=True)
    
    app.run(debug=True, port=5000)

