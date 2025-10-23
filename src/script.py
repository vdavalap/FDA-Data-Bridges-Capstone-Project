import pandas as pd
import requests
import os
import time

# --- Configuration ---

# 1. The name of your Excel file
excel_file_name = '838845ad-0ccc-4926-b523-944f9f1ca96d.xlsx'  # <--- CHANGED

# 2. The name of the column in your Excel that contains the URLs
url_column_name = 'Download'  # <--- !! IMPORTANT: Change this if your column name is different

# 3. The name of the folder where you want to save the PDFs
save_folder = 'downloads'

# --- End of Configuration ---


# Create the download folder if it doesn't already exist
os.makedirs(save_folder, exist_ok=True)

# Create a list to keep track of any failed downloads
failed_downloads = []

print(f"Reading URLs from {excel_file_name}...")
try:
    # Read the Excel file into a pandas DataFrame
    df = pd.read_excel(excel_file_name)  # <--- CHANGED
    
    # Check if the URL column exists
    if url_column_name not in df.columns:
        print(f"Error: Column '{url_column_name}' not found in {excel_file_name}.")
        print(f"Available columns are: {df.columns.tolist()}")
        exit()

    # Get the list of URLs
    urls_to_download = df[url_column_name].tolist()
    total_files = len(urls_to_download)
    print(f"Found {total_files} files to download.")

    # Loop through each URL in the list
    for i, url in enumerate(urls_to_download):
        # Clean up the URL (remove any extra spaces)
        
        if i >= 10:
            print("\nReached test limit of 10 files. Stopping.")
            break
        
        
        url = str(url).strip()
        
        if not url.startswith('http'):
            print(f"Skipping invalid URL: {url}")
            continue

        # Get a unique filename from the URL (e.g., "188200.pdf")
        try:
            # This logic splits the URL and takes the second-to-last part
            # e.g., https://.../media/188200/download -> "188200"
            file_id = url.split('/')[-2]
            filename = f"{file_id}.pdf"
            save_path = os.path.join(save_folder, filename)
        except Exception as e:
            print(f"Error: Could not create a filename for URL: {url}. Skipping. Error: {e}")
            failed_downloads.append(url)
            continue

        print(f"Downloading file {i + 1} of {total_files}: {filename}...")

        try:
            # Make the request to the URL
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }

            # Make the request to the URL, now with headers
            response = requests.get(url, headers=headers, timeout=30)

            # Check if the request was successful (Status code 200)
            if response.status_code == 200:
                # Save the file (write in binary mode 'wb')
                with open(save_path, 'wb') as f:
                    f.write(response.content)
                # print(f"Successfully saved {filename}")
            else:
                print(f"Failed to download {url}. Status code: {response.status_code}")
                failed_downloads.append(url)

            # --- BE POLITE! ---
            # Wait for 1 second before the next request to avoid
            # overloading the server (this is very important!)
            time.sleep(1)

        except requests.exceptions.RequestException as e:
            # Handle network errors, timeouts, etc.
            print(f"Error downloading {url}: {e}")
            failed_downloads.append(url)
            
except FileNotFoundError:
    print(f"Error: The file {excel_file_name} was not found.")
except Exception as e:
    print(f"An unexpected error occurred: {e}")


# --- Final Report ---
print("\n--- Download Complete ---")
if not failed_downloads:
    print("All files were downloaded successfully!")
else:
    print(f"Total failed downloads: {len(failed_downloads)}")
    print("The following URLs failed:")
    for failed_url in failed_downloads:
        print(failed_url)