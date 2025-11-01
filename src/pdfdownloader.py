import pandas as pd
import requests
import os
import time
import glob

# --- Configuration ---

# Folder where FDA output CSV files are stored
fda_outputs_folder = os.path.join(os.getcwd(), 'fda_outputs')

# Name of the column in the CSV that contains the URLs
url_column_name = 'Download'  # <-- Change this if the column name is different

# Folder to save the downloaded PDFs
save_folder = 'downloads'

# --- End of Configuration ---


def get_latest_csv(folder_path):
    """Find the most recently modified CSV file in the given folder."""
    csv_files = glob.glob(os.path.join(folder_path, '*.csv'))
    if not csv_files:
        raise FileNotFoundError(f"No CSV files found in {folder_path}")
    latest_file = max(csv_files, key=os.path.getmtime)
    return latest_file


def download_pdfs_from_csv(csv_path, url_column, output_folder):
    """Download PDFs from the given CSV file."""
    os.makedirs(output_folder, exist_ok=True)
    failed_downloads = []

    print(f"Reading URLs from {csv_path}...")
    df = pd.read_csv(csv_path)

    if url_column not in df.columns:
        print(f"Error: Column '{url_column}' not found in {csv_path}.")
        print(f"Available columns: {df.columns.tolist()}")
        return

    urls_to_download = df[url_column].dropna().tolist()
    total_files = len(urls_to_download)
    print(f"Found {total_files} URLs to download.\n")

    for i, url in enumerate(urls_to_download):
        url = str(url).strip()

        # Test limit (optional, remove if you want full download)
        if i >= 10:
            print("\nReached test limit of 10 files. Stopping.")
            break

        if not url.startswith('http'):
            print(f"Skipping invalid URL: {url}")
            continue

        try:
            file_id = url.split('/')[-2]
            filename = f"{file_id}.pdf"
            save_path = os.path.join(output_folder, filename)
        except Exception as e:
            print(f"Error creating filename for URL: {url} | Error: {e}")
            failed_downloads.append(url)
            continue

        print(f"({i + 1}/{total_files}) Downloading {filename}...")

        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                              'AppleWebKit/537.36 (KHTML, like Gecko) '
                              'Chrome/91.0.4472.124 Safari/537.36'
            }

            response = requests.get(url, headers=headers, timeout=30)

            if response.status_code == 200:
                with open(save_path, 'wb') as f:
                    f.write(response.content)
            else:
                print(f"Failed ({response.status_code}) -> {url}")
                failed_downloads.append(url)

            time.sleep(1)

        except requests.exceptions.RequestException as e:
            print(f"Error downloading {url}: {e}")
            failed_downloads.append(url)

    print("\n--- Download Complete ---")
    if not failed_downloads:
        print("✅ All files downloaded successfully!")
    else:
        print(f"⚠️ Total failed downloads: {len(failed_downloads)}")
        for failed_url in failed_downloads:
            print(f" - {failed_url}")


# --- Main Execution ---

try:
    latest_csv = get_latest_csv(fda_outputs_folder)
    print(f"📄 Latest CSV found: {os.path.basename(latest_csv)}\n")

    download_pdfs_from_csv(latest_csv, url_column_name, save_folder)

except FileNotFoundError as e:
    print(f"Error: {e}")
except Exception as e:
    print(f"Unexpected error: {e}")
