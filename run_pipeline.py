#!/usr/bin/env python3
"""
Complete FDA 483 Form Analysis Pipeline
Runs all steps: download data, download PDFs, process PDFs, fix firm names, and optionally start dashboard
"""

import os
import sys
import argparse
import subprocess
from pathlib import Path

# Try to load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # dotenv is optional
    pass

# Default directories
DEFAULT_CSV_DIR = os.environ.get('FDA_OUTPUT_DIR', './fda_outputs')
DEFAULT_PDF_DIR = os.environ.get('DOWNLOADED_PDFS_DIR', './downloaded_pdfs')
DEFAULT_RESULTS_DIR = 'results'


def check_requirements():
    """Check if required environment variables are set"""
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        print("❌ Error: OPENAI_API_KEY environment variable is required")
        print("   Set it in your .env file or export it:")
        print("   export OPENAI_API_KEY='your-key-here'")
        return False
    return True


def step_download_dashboard_data(force=False):
    """Step 1: Download FDA dashboard data (CSV)"""
    print("\n" + "="*70)
    print("STEP 1: Downloading FDA Dashboard Data")
    print("="*70)
    
    try:
        cmd = [sys.executable, 'fda_dataset_downloader.py']
        if force:
            cmd.append('--force')
        
        result = subprocess.run(cmd, check=False, capture_output=False)
        if result.returncode == 0:
            print("✓ Dashboard data downloaded successfully")
            return True
        else:
            print("⚠ Dashboard data download completed with warnings")
            return True  # Continue even if there are warnings
    except Exception as e:
        print(f"❌ Error downloading dashboard data: {e}")
        return False


def step_download_pdfs(limit=0, csv_path=None, pdf_dir=None, results_dir=None):
    """Step 2: Download PDFs from CSV data"""
    print("\n" + "="*70)
    print("STEP 2: Downloading PDFs")
    print("="*70)
    
    try:
        cmd = [sys.executable, 'download_pdfs.py']
        
        if csv_path:
            cmd.extend(['--csv', str(csv_path)])
        
        if pdf_dir:
            cmd.extend(['--output', str(pdf_dir)])
        
        if results_dir:
            cmd.extend(['--results-dir', str(results_dir)])
        
        if limit > 0:
            cmd.extend(['--limit', str(limit)])
        
        result = subprocess.run(cmd, check=False, capture_output=False)
        if result.returncode == 0:
            print("✓ PDFs downloaded successfully")
            return True
        else:
            print("⚠ PDF download completed with warnings")
            return True
    except Exception as e:
        print(f"❌ Error downloading PDFs: {e}")
        return False


def step_process_pdfs(pdf_dir=None, results_dir=None, csv_dir=None, keep_pdfs=False):
    """Step 3: Process PDFs and generate JSON results"""
    print("\n" + "="*70)
    print("STEP 3: Processing PDFs")
    print("="*70)
    
    if not pdf_dir:
        pdf_dir = DEFAULT_PDF_DIR
    
    if not results_dir:
        results_dir = DEFAULT_RESULTS_DIR
    
    # Check if PDF directory exists and has PDFs
    pdf_path = Path(pdf_dir)
    if not pdf_path.exists():
        print(f"⚠ PDF directory not found: {pdf_dir}")
        print("  Skipping PDF processing step")
        return True
    
    pdf_files = list(pdf_path.glob('*.pdf'))
    if not pdf_files:
        print(f"⚠ No PDF files found in {pdf_dir}")
        print("  Skipping PDF processing step")
        return True
    
    print(f"  Found {len(pdf_files)} PDF files to process")
    
    try:
        cmd = [sys.executable, 'run_analysis.py', '--folder', str(pdf_dir)]
        cmd.extend(['--output', str(results_dir)])
        
        if csv_dir:
            cmd.extend(['--csv', str(csv_dir)])
        
        if keep_pdfs:
            cmd.append('--keep-pdfs')
        
        result = subprocess.run(cmd, check=False, capture_output=False)
        if result.returncode == 0:
            print("✓ PDFs processed successfully")
            return True
        else:
            print("⚠ PDF processing completed with warnings")
            return True
    except Exception as e:
        print(f"❌ Error processing PDFs: {e}")
        return False


def step_fix_firm_names(results_dir=None, csv_dir=None):
    """Step 4: Fix firm names using CSV data"""
    print("\n" + "="*70)
    print("STEP 4: Fixing Firm Names")
    print("="*70)
    
    if not results_dir:
        results_dir = DEFAULT_RESULTS_DIR
    
    # Check if results directory exists
    results_path = Path(results_dir)
    if not results_path.exists():
        print(f"⚠ Results directory not found: {results_dir}")
        print("  Skipping firm name fixing step")
        return True
    
    result_files = list(results_path.glob('*_result.json'))
    if not result_files:
        print(f"⚠ No result JSON files found in {results_dir}")
        print("  Skipping firm name fixing step")
        return True
    
    print(f"  Found {len(result_files)} result files to update")
    
    try:
        # Import and run fix_firm_names directly
        from fix_firm_names import create_firm_mapping_from_csv, update_result_files
        from fda_483_processor import FDA483Processor
        
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            print("❌ Error: OPENAI_API_KEY required for firm name fixing")
            return False
        
        processor = FDA483Processor(api_key=api_key)
        firm_mapping = {}
        
        # Try CSV first
        csv_path = csv_dir or DEFAULT_CSV_DIR
        print(f"  Loading CSV data from: {csv_path}")
        csv_mapping = create_firm_mapping_from_csv(csv_path)
        if csv_mapping:
            firm_mapping = csv_mapping
            print(f"  Loaded {len(firm_mapping)} firm mappings from CSV")
        else:
            print("  ⚠ No CSV mapping found")
        
        if not firm_mapping:
            print("  ⚠ No firm mapping data available, skipping firm name updates")
            return True
        
        # Update result files
        updated_count, from_data_count, extracted_count, reprocessed_count = update_result_files(
            str(results_dir), firm_mapping, processor
        )
        
        print(f"✓ Updated {updated_count} result files")
        print(f"  - From CSV/Excel: {from_data_count}")
        print(f"  - Extracted from PDFs: {extracted_count}")
        if reprocessed_count > 0:
            print(f"  - Reprocessed PDFs: {reprocessed_count}")
        
        return True
    except Exception as e:
        print(f"❌ Error fixing firm names: {e}")
        import traceback
        traceback.print_exc()
        return False


def step_start_dashboard(port=5000):
    """Step 5: Start the dashboard (optional)"""
    print("\n" + "="*70)
    print("STEP 5: Starting Dashboard")
    print("="*70)
    
    try:
        print(f"  Starting dashboard on http://localhost:{port}")
        print("  Press Ctrl+C to stop the dashboard")
        cmd = [sys.executable, 'dashboard.py']
        subprocess.run(cmd, check=False)
    except KeyboardInterrupt:
        print("\n✓ Dashboard stopped by user")
        return True
    except Exception as e:
        print(f"❌ Error starting dashboard: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description='Run complete FDA 483 Form Analysis Pipeline',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run complete pipeline (download data, PDFs, process, fix names)
  python run_pipeline.py

  # Run pipeline with limit on PDF downloads
  python run_pipeline.py --pdf-limit 50

  # Run pipeline and start dashboard
  python run_pipeline.py --start-dashboard

  # Skip specific steps
  python run_pipeline.py --skip-download --skip-pdfs

  # Keep PDFs after processing
  python run_pipeline.py --keep-pdfs

  # Force re-download of dashboard data
  python run_pipeline.py --force-download
        """
    )
    
    # Step control
    parser.add_argument('--skip-download', action='store_true',
                       help='Skip downloading dashboard data')
    parser.add_argument('--skip-pdfs', action='store_true',
                       help='Skip downloading PDFs')
    parser.add_argument('--skip-process', action='store_true',
                       help='Skip processing PDFs')
    parser.add_argument('--skip-fix-names', action='store_true',
                       help='Skip fixing firm names')
    
    # Options
    parser.add_argument('--pdf-limit', type=int, default=0,
                       help='Limit number of PDFs to download (0 = all, default: 0)')
    parser.add_argument('--force-download', action='store_true',
                       help='Force re-download of dashboard data even if CSV exists')
    parser.add_argument('--keep-pdfs', action='store_true',
                       help='Keep PDF files after processing (default: delete)')
    parser.add_argument('--start-dashboard', action='store_true',
                       help='Start dashboard after pipeline completes')
    parser.add_argument('--dashboard-port', type=int, default=5000,
                       help='Port for dashboard (default: 5000)')
    
    # Paths
    parser.add_argument('--csv-dir', type=str, default=None,
                       help=f'CSV data directory (default: {DEFAULT_CSV_DIR})')
    parser.add_argument('--pdf-dir', type=str, default=None,
                       help=f'PDF directory (default: {DEFAULT_PDF_DIR})')
    parser.add_argument('--results-dir', type=str, default=None,
                       help=f'Results directory (default: {DEFAULT_RESULTS_DIR})')
    parser.add_argument('--csv-path', type=str, default=None,
                       help='Specific CSV file path (overrides --csv-dir)')
    
    args = parser.parse_args()
    
    # Check requirements
    if not check_requirements():
        sys.exit(1)
    
    print("\n" + "="*70)
    print("FDA 483 FORM ANALYSIS PIPELINE")
    print("="*70)
    print(f"CSV Directory: {args.csv_dir or DEFAULT_CSV_DIR}")
    print(f"PDF Directory: {args.pdf_dir or DEFAULT_PDF_DIR}")
    print(f"Results Directory: {args.results_dir or DEFAULT_RESULTS_DIR}")
    print(f"PDF Limit: {args.pdf_limit if args.pdf_limit > 0 else 'Unlimited'}")
    print(f"Keep PDFs: {args.keep_pdfs}")
    print("="*70)
    
    # Run pipeline steps
    success = True
    
    # Step 1: Download dashboard data
    if not args.skip_download:
        if not step_download_dashboard_data(force=args.force_download):
            print("\n❌ Pipeline failed at Step 1: Download Dashboard Data")
            sys.exit(1)
    else:
        print("\n⏭ Skipping Step 1: Download Dashboard Data")
    
    # Step 2: Download PDFs
    if not args.skip_pdfs:
        csv_path = args.csv_path
        if not csv_path and args.csv_dir:
            # Find latest CSV in directory
            csv_dir = Path(args.csv_dir or DEFAULT_CSV_DIR)
            csv_files = sorted(csv_dir.glob('*.csv'), key=lambda p: p.stat().st_mtime, reverse=True)
            if csv_files:
                csv_path = str(csv_files[0])
        
        if not step_download_pdfs(limit=args.pdf_limit, csv_path=csv_path, 
                                 pdf_dir=args.pdf_dir, results_dir=args.results_dir):
            print("\n❌ Pipeline failed at Step 2: Download PDFs")
            sys.exit(1)
    else:
        print("\n⏭ Skipping Step 2: Download PDFs")
    
    # Step 3: Process PDFs
    if not args.skip_process:
        csv_dir = args.csv_dir or DEFAULT_CSV_DIR
        if not step_process_pdfs(pdf_dir=args.pdf_dir, results_dir=args.results_dir, 
                                csv_dir=csv_dir, keep_pdfs=args.keep_pdfs):
            print("\n❌ Pipeline failed at Step 3: Process PDFs")
            sys.exit(1)
    else:
        print("\n⏭ Skipping Step 3: Process PDFs")
    
    # Step 4: Fix firm names
    if not args.skip_fix_names:
        csv_dir = args.csv_dir or DEFAULT_CSV_DIR
        if not step_fix_firm_names(results_dir=args.results_dir, csv_dir=csv_dir):
            print("\n⚠ Pipeline completed with warnings at Step 4: Fix Firm Names")
            # Don't exit on error, just warn
    else:
        print("\n⏭ Skipping Step 4: Fix Firm Names")
    
    # Step 5: Start dashboard (optional)
    if args.start_dashboard:
        step_start_dashboard(port=args.dashboard_port)
    
    # Summary
    print("\n" + "="*70)
    print("PIPELINE COMPLETE")
    print("="*70)
    print(f"Results saved to: {args.results_dir or DEFAULT_RESULTS_DIR}")
    if not args.start_dashboard:
        print("\nTo start the dashboard, run:")
        print("  python dashboard.py")
        print("\nOr use:")
        print("  python run_pipeline.py --start-dashboard")
    print("="*70)


if __name__ == '__main__':
    main()

