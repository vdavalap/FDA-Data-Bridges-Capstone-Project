"""
Main script to run 483 form analysis
Process PDFs and generate classifications
"""

import os
import sys
from fda_483_processor import FDA483Processor
import argparse
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    print("Error: OpenAI API key required.")
    exit(1)

def main():
    parser = argparse.ArgumentParser(description='Process FDA 483 forms')
    parser.add_argument('--pdf', type=str, help='Path to single PDF file')
    parser.add_argument('--folder', type=str, help='Path to folder containing PDFs')
    parser.add_argument('--firm', type=str, help='Firm name')
    parser.add_argument('--fei', type=str, help='FEI number')
    parser.add_argument('--output', type=str, default='results', help='Output folder for results')
    parser.add_argument('--api-key', type=str, help='OpenAI API key (or set OPENAI_API_KEY env var)')
    parser.add_argument('--csv', type=str, help='Path to CSV file or directory with CSV files from fda_dashboard_downloader.py')
    parser.add_argument('--keep-pdfs', action='store_true', help='Keep PDF files after processing (default: delete PDFs after JSON extraction)')
    
    args = parser.parse_args()
    
    # Check for API key
    api_key = args.api_key or os.getenv('OPENAI_API_KEY')
    if not api_key:
        print("Error: OpenAI API key required.")
        print("Set OPENAI_API_KEY environment variable or use --api-key argument")
        sys.exit(1)
    
    # Initialize processor with CSV data if provided
    csv_path = args.csv or os.environ.get('FDA_OUTPUT_DIR', './fda_outputs')
    processor = FDA483Processor(api_key=api_key, csv_data_path=csv_path)
    
    # Create output folder
    os.makedirs(args.output, exist_ok=True)
    
    firm_info = {}
    if args.firm:
        firm_info['firm'] = args.firm
    if args.fei:
        firm_info['fei'] = args.fei
    
    # Process single file or batch
    if args.pdf:
        print(f"Processing single PDF: {args.pdf}")
        try:
            result = processor.process_483_form(args.pdf, firm_info)
            
            # Save result
            output_file = os.path.join(args.output, f"{os.path.basename(args.pdf).replace('.pdf', '')}_result.json")
            processor.save_results(result, output_file)
            
            # Delete PDF after processing if not keeping
            if not args.keep_pdfs:
                try:
                    os.remove(args.pdf)
                    print(f"  ✓ Deleted PDF: {os.path.basename(args.pdf)}")
                except Exception as e:
                    print(f"  ⚠ Could not delete PDF: {e}")
            
            print(f"\n✓ Successfully processed {args.pdf}")
            print(f"  Classification: {result.get('overall_classification')}")
            print(f"  Violations: {len(result.get('violations', []))}")
            print(f"  Results saved to: {output_file}")
            
        except Exception as e:
            print(f"Error processing {args.pdf}: {str(e)}")
            sys.exit(1)
    
    elif args.folder:
        print(f"Processing batch from folder: {args.folder}")
        delete_pdfs = not args.keep_pdfs
        if delete_pdfs:
            print("  PDFs will be deleted after successful JSON extraction")
        else:
            print("  PDFs will be kept (--keep-pdfs flag set)")
        
        results = processor.process_batch(args.folder, args.output, None, csv_data_path=csv_path, delete_pdfs_after_processing=delete_pdfs)
        
        successful = sum(1 for r in results if r['status'] == 'success')
        failed = sum(1 for r in results if r['status'] == 'error')
        
        print(f"\n✓ Batch processing complete")
        print(f"  Successful: {successful}")
        print(f"  Failed: {failed}")
        print(f"  Results saved to: {args.output}")
    
    else:
        print("Error: Must specify either --pdf or --folder")
        parser.print_help()
        sys.exit(1)

if __name__ == "__main__":
    main()

