import argparse
import os
import time
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
import requests

CSV_OUTPUT_DIR = Path(os.environ.get("FDA_OUTPUT_DIR", "fda_outputs"))


def download_pdf_from_url(url, output_folder, filename=None):
    """
    Download a PDF file from a URL and save it to the output folder.

    Args:
        url: The URL to download from
        output_folder: The folder to save the PDF to
        filename: Optional custom filename. If not provided, extracts from URL.

    Returns:
        tuple: (success: bool, filename: str, error_message: str)
    """
    try:
        os.makedirs(output_folder, exist_ok=True)

        if filename is None:
            parsed_url = urlparse(url)
            path_parts = parsed_url.path.split("/")
            media_id = None
            for i, part in enumerate(path_parts):
                if part == "media" and i + 1 < len(path_parts):
                    media_id = path_parts[i + 1]
                    break

            if media_id:
                filename = f"FDA_{media_id}.pdf"
            else:
                filename = f"download_{int(time.time())}.pdf"

        if not filename.endswith(".pdf"):
            filename += ".pdf"

        filepath = os.path.join(output_folder, filename)

        if os.path.exists(filepath):
            return (True, filename, "File already exists")

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        response = requests.get(url, headers=headers, stream=True, timeout=30)
        response.raise_for_status()

        with open(filepath, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        return (True, filename, None)

    except requests.exceptions.RequestException as e:
        return (False, None, f"Request error: {str(e)}")
    except Exception as e:  # noqa: BLE001 - generic fallback
        return (False, None, f"Error: {str(e)}")


def find_latest_csv(csv_directory: Path) -> Path | None:
    csv_files = sorted(
        csv_directory.glob("*.csv"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return csv_files[0] if csv_files else None


def load_dashboard_downloads(csv_path: Path, download_column: str) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    if download_column not in df.columns:
        raise KeyError(
            f"Column '{download_column}' not found. Available: {list(df.columns)}"
        )
    return df


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download Form 483 PDFs using URLs exported from the FDA dashboard.",
    )
    parser.add_argument(
        "--csv",
        type=Path,
        help="Path to CSV export from the dashboard. Defaults to latest file in FDA_OUTPUT_DIR.",
    )
    parser.add_argument(
        "--download-column",
        default="Download",
        help="Column containing PDF URLs (default: Download).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("downloaded_pdfs"),
        help="Directory to store downloaded PDFs (default: downloaded_pdfs).",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.5,
        help="Delay between downloads in seconds (default: 0.5).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        metavar="N",
        help="Maximum number of PDFs to download (default: 0 = download all). Use 0 for no limit. Example: --limit 50",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    csv_path = args.csv
    if csv_path is None:
        csv_path = find_latest_csv(CSV_OUTPUT_DIR)
        if csv_path is None:
            print(
                f"No CSV files found in {CSV_OUTPUT_DIR.resolve()}. "
                "Run fda_dashboard_downloader.py first or pass --csv."
            )
            return

    if not csv_path.exists():
        print(f"CSV file not found: {csv_path}")
        return

    print(f"Reading dashboard export: {csv_path}")
    try:
        df = load_dashboard_downloads(csv_path, args.download_column)
        print(f"Found {len(df)} rows in the CSV file")
    except Exception as e:  # noqa: BLE001
        print(f"Error reading CSV file: {e}")
        return

    urls = df[args.download_column].dropna().tolist()
    total_urls = len(urls)
    
    output_path = args.output
    output_path.mkdir(exist_ok=True)
    
    # Filter out URLs that would result in already-downloaded PDFs
    existing_pdfs = set()
    for pdf_file in output_path.glob("*.pdf"):
        existing_pdfs.add(pdf_file.name)
    
    # Extract media IDs from URLs to check if PDF already exists
    def get_pdf_filename_from_url(url: str) -> str:
        """Extract expected PDF filename from URL"""
        parsed_url = urlparse(url)
        path_parts = parsed_url.path.split("/")
        media_id = None
        for i, part in enumerate(path_parts):
            if part == "media" and i + 1 < len(path_parts):
                media_id = path_parts[i + 1]
                break
        if media_id:
            return f"FDA_{media_id}.pdf"
        return None
    
    # Filter URLs to only include those not already downloaded
    new_urls = []
    skipped_count = 0
    for url in urls:
        if pd.isna(url) or not isinstance(url, str) or not url.strip():
            continue
        expected_filename = get_pdf_filename_from_url(url.strip())
        if expected_filename and expected_filename in existing_pdfs:
            skipped_count += 1
            continue
        new_urls.append(url)
    
    urls = new_urls
    
    # Apply limit if specified
    limit = max(args.limit, 0)
    if limit > 0:
        urls = urls[:limit]
        print(f"Total URLs in CSV: {total_urls}")
        if skipped_count > 0:
            print(f"Skipped {skipped_count} already downloaded PDFs")
        print(f"Limit applied: Downloading {len(urls)} new PDFs (limit: {limit})")
    else:
        print(f"Total URLs in CSV: {total_urls}")
        if skipped_count > 0:
            print(f"Skipped {skipped_count} already downloaded PDFs")
        print(f"Found {len(urls)} new URLs to download (no limit)")

    print(f"Saving files to: {output_path.resolve()}")

    successful = 0
    failed = 0
    skipped_during_download = 0

    for idx, url in enumerate(urls, 1):
        if pd.isna(url) or not isinstance(url, str) or not url.strip():
            print(f"Skipping row {idx}: Empty or invalid URL")
            continue

        cleaned_url = url.strip()
        print(f"[{idx}/{len(urls)}] Downloading: {cleaned_url}")

        success, filename, error = download_pdf_from_url(
            cleaned_url, str(output_path)
        )

        if success:
            if error == "File already exists":
                print(f"  ⊘ Skipped (already exists): {filename}")
                skipped_during_download += 1
            else:
                print(f"  ✓ Successfully saved: {filename}")
                successful += 1
        else:
            print(f"  ✗ Failed: {error}")
            failed += 1

        time.sleep(max(args.delay, 0.0))

    print("\n" + "=" * 50)
    print("Download Summary:")
    print(f"  New downloads: {successful}")
    print(f"  Already existed: {skipped_count + skipped_during_download}")
    print(f"  Failed: {failed}")
    print(f"  Total processed: {len(urls)}")
    if limit > 0 and total_urls > limit:
        print(f"  Remaining in CSV: {total_urls - limit} (use --limit 0 to download all)")
    print(f"  Files saved to: {output_path.resolve()}")
    print("=" * 50)


if __name__ == "__main__":
    main()