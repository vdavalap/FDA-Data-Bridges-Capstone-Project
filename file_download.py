import requests
from bs4 import BeautifulSoup
import os

# URL of the FDA page
url = "https://www.fda.gov/about-fda/office-inspections-and-investigations/oii-foia-electronic-reading-room"

# Add headers to mimic a browser request
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Accept-Language': 'en-US,en;q=0.9',
    'Referer': 'https://www.google.com/', # Can sometimes help
    'DNT': '1', # Do Not Track Request Header
}


# Fetch the page content
response = requests.get(url, headers=headers)
response.raise_for_status()  # Raise an exception for bad status codes

# Parse the page content
soup = BeautifulSoup(response.content, 'html.parser')

# Find all the 483 hyperlinks
# This assumes the links still contain "483" in their text or href
links = soup.find_all('a', href=True)

# Filter for links that are likely the 483 documents
four_eight_three_links = [link['href'] for link in links if '483' in link.get_text() or '483' in link['href']]

# Create a directory to save the downloaded files
download_dir = '/content/fda_483_downloads'
os.makedirs(download_dir, exist_ok=True)

# Download the files
for file_url in four_eight_three_links:
    # Ensure the URL is absolute
    if not file_url.startswith('http'):
        file_url = requests.compat.urljoin(url, file_url)

    print(f"Downloading from: {file_url}")

    try:
        file_response = requests.get(file_url, stream=True, headers=headers) # Also add headers to file download
        file_response.raise_for_status()

        filename = file_url.split("/")[-1]
        filepath = os.path.join(download_dir, filename)

        with open(filepath, 'wb') as f:
            for chunk in file_response.iter_content(chunk_size=8192):
                f.write(chunk)

        print(f"Downloaded {filename} to {filepath}")

    except requests.exceptions.RequestException as e:
        print(f"Error downloading {file_url}: {e}")

print("Download process finished.")