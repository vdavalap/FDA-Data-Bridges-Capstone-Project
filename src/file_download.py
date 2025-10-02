import os
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service as ChromeService

# --- CONFIGURATION ---
URL = "https://www.fda.gov/about-fda/office-inspections-and-investigations/oii-foia-electronic-reading-room"
DOWNLOAD_LIMIT = 20  # The maximum number of PDFs to download
DOWNLOAD_DIR = os.path.join(os.getcwd(), "data", "raw")
RECORD_TYPES = ["483", "Establishment Inspection Report (EIR"]

# Create the download directory if it doesn't exist
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# --- SELENIUM SETUP ---
def setup_driver():
    """Sets up the Chrome driver with automatic PDF download preferences."""
    print("Setting up Chrome driver...")
    
    # Configure Chrome options to auto-download PDFs and disable the PDF viewer
    chrome_options = webdriver.ChromeOptions()
    prefs = {
        "download.default_directory": DOWNLOAD_DIR,
        "download.prompt_for_download": False,
        "plugins.always_open_pdf_externally": True,  # Auto-download PDFs instead of opening
        "safebrowsing.enabled": True
    }
    chrome_options.add_experimental_option("prefs", prefs)
    # chrome_options.add_argument("--headless") # Remove the hash tag if you want it to run without a visible browser
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
    
    # Initialize the Chrome Driver
    service = ChromeService(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    driver.implicitly_wait(10)
    return driver

# --- SCRAPING LOGIC ---

def download_filtered_records(driver):
    """Filters the table and downloads the specified number of records from the visible page."""
    
    print(f"Navigating to: {URL}")
    driver.get(URL)
    
    wait = WebDriverWait(driver, 20)
    
    # --- LOCATE FILTER DROPDOWN ---
    try:
        # XPath to find the <select> element that immediately follows the 'FOIA Record Type' label
        record_type_dropdown = wait.until(
            EC.presence_of_element_located((By.XPATH, "//label[contains(text(), 'FOIA Record Type')]/following-sibling::select"))
        )
    except:
        # Fallback in case the XPath fails (e.g., if the FDA changes the label text)
        print("Could not find filter by label. Waiting for table to appear...")
        wait.until(EC.presence_of_element_located((By.XPATH, "//table[contains(@class, 'datatable')]")))
        print("Table loaded. Please manually verify the XPath for the filter if the script fails.")
        return

    select = Select(record_type_dropdown)
    
    download_count = 0
    
    for record_type in RECORD_TYPES:
        if download_count >= DOWNLOAD_LIMIT:
            break
            
        print(f"\n--- Applying Filter: {record_type} ---")
        
        # 1. Select the record type and wait for the table to reload
        select.select_by_visible_text(record_type)
        time.sleep(5) # Give extra time for the dynamic table to fully filter and load
        
        # 2. Get the updated table rows that are *currently visible*
        # This XPath selects all non-header rows in the main table body
        row_xpath = "//table[contains(@class, 'datatable')]/tbody/tr"
        
        # Wait for the first row of the *filtered* table to appear
        wait.until(EC.presence_of_element_located((By.XPATH, row_xpath)))
        
        # Find all current visible rows in the table. This should be limited to the first page (usually 10, 25, or 50)
        rows_on_page = driver.find_elements(By.XPATH, row_xpath)
        
        print(f"Found {len(rows_on_page)} visible entries for {record_type} on the current page.")
        
        for i in range(len(rows_on_page)):
            if download_count >= DOWNLOAD_LIMIT:
                print(f"Stopping at limit of {DOWNLOAD_LIMIT} downloads.")
                break
                
            # Re-find the rows *inside* the loop for stability (avoids StaleElementReferenceException)
            current_rows = driver.find_elements(By.XPATH, row_xpath)
            
            # --- Locate the downloadable PDF link in the row ---
            try:
                # The link is expected to be a direct link to the document.
                # We target the first <a> tag found in the current row
                link_element = current_rows[i].find_element(By.TAG_NAME, 'a')
                link_text = link_element.text
                
                print(f"[{download_count + 1}/{DOWNLOAD_LIMIT}] Initiating download for: {link_text}...")
                
                # Use execute_script to click the element; this is generally more robust 
                # on complex or government websites than a standard .click()
                driver.execute_script("arguments[0].click();", link_element)
                
                download_count += 1
                time.sleep(3) # Wait for the download to initiate (important!)
                
            except Exception as e:
                # This catches if a row is a status message (e.g., 'No data available') or just lacks a link
                print(f"Skipping row {i+1} for {record_type}: No clickable link or download initiated.")
                
        # 3. Clear the filter for the next iteration (if needed)
        if record_type != RECORD_TYPES[-1] and download_count < DOWNLOAD_LIMIT:
            print("Clearing filter to move to next record type...")
            select.select_by_visible_text('- Any -')
            time.sleep(3)
        
    print("\n--- Process Finished ---")
    print(f"Successfully initiated download for {download_count} of {DOWNLOAD_LIMIT} documents to the folder: {DOWNLOAD_DIR}")
    
    # Final check for in-progress downloads
    time.sleep(5) 
    if any(".crdownload" in f for f in os.listdir(DOWNLOAD_DIR)):
        print("\nNote: Some files may still be downloading (look for .crdownload files). Wait for all files to complete.")


# --- MAIN EXECUTION ---
if __name__ == "__main__":
    driver = setup_driver()
    try:
        download_filtered_records(driver)
    finally:
        driver.quit()