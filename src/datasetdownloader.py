#!/usr/bin/env python3
"""
FDA Dashboard downloader (robust + minimal scope):
- Launches headless Chrome (Selenium + webdriver-manager)
- Opens https://datadashboard.fda.gov/oii/cd/inspections.htm
- Opens "Download Dataset" section
- Finds dataset links in top page AND any iframes
- Tries three click strategies (normal, Actions, JS)
- If still not interactable, extracts direct .xlsx hrefs and downloads via requests
- Waits for .xlsx/.xls downloads to complete
- Converts downloaded Excel files to CSV in OUTPUT_DIR

Requirements:
    pip install selenium webdriver-manager pandas openpyxl requests

Environment variables (optional):
    FDA_DL_DIR     - download directory (default: ./fda_dashboard_downloads)
    FDA_OUTPUT_DIR - output directory   (default: ./fda_outputs)
"""

import os
import time
import glob
import shutil
import pathlib
import logging
from typing import List, Tuple, Set
import requests

import pandas as pd

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.common.exceptions import (
    TimeoutException, NoSuchElementException, WebDriverException
)
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.action_chains import ActionChains
from webdriver_manager.chrome import ChromeDriverManager

DASHBOARD_URL = "https://datadashboard.fda.gov/oii/cd/inspections.htm"
DOWNLOAD_DIR = os.path.abspath(os.environ.get("FDA_DL_DIR", "./fda_dashboard_downloads"))
OUTPUT_DIR = os.path.abspath(os.environ.get("FDA_OUTPUT_DIR", "./fda_outputs"))
WAIT_SECS = 35
DOWNLOAD_TIMEOUT_SECS = 300

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

def ensure_dirs():
    pathlib.Path(DOWNLOAD_DIR).mkdir(parents=True, exist_ok=True)
    pathlib.Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
    logging.info(f"DOWNLOAD_DIR = {DOWNLOAD_DIR}")
    logging.info(f"OUTPUT_DIR   = {OUTPUT_DIR}")

def chrome_driver(download_dir: str) -> webdriver.Chrome:
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1600,1200")
    chrome_options.add_argument("--disable-dev-shm-usage")
    prefs = {
        "download.default_directory": download_dir,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "plugins.always_open_pdf_externally": True,
        "safebrowsing.enabled": True,
    }
    chrome_options.add_experimental_option("prefs", prefs)
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    driver.set_page_load_timeout(120)
    return driver

def open_download_tab(driver: webdriver.Chrome):
    wait = WebDriverWait(driver, WAIT_SECS)
    try:
        elem = wait.until(EC.presence_of_element_located(
            (By.XPATH, "//a[contains(., 'Download Dataset')] | //button[contains(., 'Download Dataset')]")
        ))
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", elem)
        try:
            elem.click()
        except Exception:
            driver.execute_script("arguments[0].click();", elem)
        logging.info("Opened 'Download Dataset' section")
    except TimeoutException:
        logging.warning("Could not find a distinct 'Download Dataset' tab; continuing.")

def _candidate_link_elements(driver: webdriver.Chrome) -> List:
    # We consider both specific text and generic “Entire Dataset” plus direct .xlsx links
    xpaths = [
        "//a[normalize-space()='Entire Inspections Dataset']",
        "//a[normalize-space()='Entire Citations Dataset']",
        "//a[normalize-space()='Entire Dataset']",
        "//a[contains(@href,'.xlsx') or contains(@href,'.xls')]",
        "//button[contains(.,'Entire')]",
    ]
    elems = []
    for xp in xpaths:
        elems.extend(driver.find_elements(By.XPATH, xp))
    # De-duplicate by id
    uniq = []
    seen = set()
    for e in elems:
        try:
            key = e.id
        except Exception:
            key = id(e)
        if key not in seen:
            seen.add(key)
            uniq.append(e)
    return uniq

def _click_element(driver: webdriver.Chrome, el) -> bool:
    # try normal click, actions, JS click
    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
        time.sleep(0.5)
        el.click()
        return True
    except Exception:
        pass
    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
        ActionChains(driver).move_to_element(el).pause(0.2).click().perform()
        return True
    except Exception:
        pass
    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
        driver.execute_script("arguments[0].click();", el)
        return True
    except Exception:
        return False

def _collect_xlsx_hrefs(driver: webdriver.Chrome) -> Set[str]:
    hrefs = set()
    for a in driver.find_elements(By.XPATH, "//a[contains(@href,'.xlsx') or contains(@href,'.xls')]"):
        try:
            href = a.get_attribute("href")
            if href:
                hrefs.add(href)
        except Exception:
            continue
    return hrefs

def _http_download(url: str, dest_dir: str) -> str:
    # simple http get to save xlsx
    local = os.path.join(dest_dir, os.path.basename(url.split("?")[0]))
    headers = {"User-Agent": "Mozilla/5.0"}
    with requests.get(url, stream=True, timeout=90, headers=headers) as r:
        r.raise_for_status()
        with open(local, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
    return local

def attempt_downloads(driver: webdriver.Chrome) -> Tuple[List[str], Set[str]]:
    """
    Clicks across top context and all iframes.
    Returns (clicked_labels, discovered_direct_xlsx_hrefs)
    """
    clicked_labels: List[str] = []
    discovered: Set[str] = set()

    # Try in top context first
    for el in _candidate_link_elements(driver):
        label = (el.text or "").strip() or el.get_attribute("aria-label") or el.get_attribute("href") or "link"
        ok = _click_element(driver, el)
        if ok:
            clicked_labels.append(label)
            time.sleep(2)

    # Collect any direct hrefs we can see
    discovered |= _collect_xlsx_hrefs(driver)

    # Try each iframe
    iframes = driver.find_elements(By.TAG_NAME, "iframe")
    logging.info(f"Iframes found: {len(iframes)}")
    for i, frame in enumerate(iframes):
        try:
            driver.switch_to.frame(frame)
        except WebDriverException:
            continue
        try:
            for el in _candidate_link_elements(driver):
                label = (el.text or "").strip() or el.get_attribute("aria-label") or el.get_attribute("href") or f"iframe[{i}] link"
                ok = _click_element(driver, el)
                if ok:
                    clicked_labels.append(label)
                    time.sleep(2)
            discovered |= _collect_xlsx_hrefs(driver)
        finally:
            driver.switch_to.default_content()

    logging.info(f"Clicked labels: {clicked_labels}")
    logging.info(f"Discovered direct .xlsx/.xls hrefs: {list(discovered)}")
    return clicked_labels, discovered

def wait_for_downloads(download_dir: str, timeout: int = DOWNLOAD_TIMEOUT_SECS) -> List[str]:
    """Wait until all .crdownload temp files disappear or timeout."""
    logging.info("Waiting for downloads to complete...")
    start = time.time()
    while time.time() - start < timeout:
        partials = glob.glob(os.path.join(download_dir, "*.crdownload"))
        if not partials:
            break
        time.sleep(2)
    files = [f for f in glob.glob(os.path.join(download_dir, "*")) if os.path.isfile(f)]
    logging.info(f"Downloaded files: {[os.path.basename(f) for f in files]}")
    return files

def convert_excels_to_csv(in_paths: List[str], out_dir: str) -> List[str]:
    csv_paths = []
    for p in in_paths:
        base = os.path.basename(p)
        stem, ext = os.path.splitext(base)
        if ext.lower() in [".xlsx", ".xls"]:
            out_csv = os.path.join(out_dir, f"{stem}.csv")
            try:
                df = pd.read_excel(p, engine="openpyxl")
                df.to_csv(out_csv, index=False)
                logging.info(f"Converted {base} -> {os.path.basename(out_csv)}")
                csv_paths.append(out_csv)
            except Exception as e:
                logging.warning(f"Failed to convert {base} to CSV: {e}")
    return csv_paths

def main():
    ensure_dirs()
    driver = chrome_driver(DOWNLOAD_DIR)

    try:
        driver.get(DASHBOARD_URL)
        logging.info("Opened dashboard page")

        open_download_tab(driver)

        clicked_labels, hrefs = attempt_downloads(driver)

        # If nothing downloaded after clicks, try HTTP downloading discovered hrefs
        pre = set(glob.glob(os.path.join(DOWNLOAD_DIR, "*")))
        if not clicked_labels:
            logging.warning("No clickable links worked; attempting HTTP downloads for discovered .xlsx URLs.")
        for url in hrefs:
            try:
                saved = _http_download(url, DOWNLOAD_DIR)
                logging.info(f"HTTP-downloaded: {saved}")
            except Exception as e:
                logging.warning(f"HTTP download failed for {url}: {e}")

        downloaded = wait_for_downloads(DOWNLOAD_DIR, DOWNLOAD_TIMEOUT_SECS)

        # Move all finished files into OUTPUT_DIR
        moved = []
        for f in downloaded:
            dest = os.path.join(OUTPUT_DIR, os.path.basename(f))
            try:
                shutil.move(f, dest)
            except Exception:
                shutil.copy2(f, dest)
                os.remove(f)
            moved.append(dest)

        # Convert Excel(s) to CSV
        csvs = convert_excels_to_csv(moved, OUTPUT_DIR)

        logging.info("Done.")
        print("\nOutputs:")
        for p in moved:
            print(" - saved:", p)
        for p in csvs:
            print(" - csv  :", p)

    finally:
        try:
            driver.quit()
        except Exception:
            pass

if __name__ == "__main__":
    main()

