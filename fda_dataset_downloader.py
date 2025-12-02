#!/usr/bin/env python3
"""
Automated FDA Form 483 downloader.

- Launches headless Chrome (Selenium + webdriver-manager)
- Opens https://datadashboard.fda.gov/oii/cd/inspections.htm
- Opens "Download Dataset" section
- Finds dataset links in top page AND any iframes
- Tries three click strategies (normal, Actions, JS)
- If still not interactable, extracts direct .xlsx hrefs and downloads via requests
- Waits for .xlsx/.xls downloads to complete
- Converts downloaded Excel files to CSV in OUTPUT_DIR

Environment variables (optional):
    FDA_DL_DIR     - download directory (default: ./fda_dashboard_downloads)
    FDA_OUTPUT_DIR - output directory   (default: ./fda_outputs)
"""

from __future__ import annotations

import glob
import logging
import os
import pathlib
from pathlib import Path
import shutil
import time
from typing import List, Set, Tuple

import pandas as pd
import requests
from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver import Chrome
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
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


def ensure_dirs() -> None:
    pathlib.Path(DOWNLOAD_DIR).mkdir(parents=True, exist_ok=True)
    pathlib.Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
    logging.info("DOWNLOAD_DIR = %s", DOWNLOAD_DIR)
    logging.info("OUTPUT_DIR   = %s", OUTPUT_DIR)


def chrome_driver(download_dir: str) -> Chrome:
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


def open_download_tab(driver: Chrome) -> None:
    wait = WebDriverWait(driver, WAIT_SECS)
    try:
        elem = wait.until(
            EC.presence_of_element_located(
                (
                    By.XPATH,
                    "//a[contains(., 'Download Dataset')] | "
                    "//button[contains(., 'Download Dataset')]",
                )
            )
        )
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", elem)
        try:
            elem.click()
        except Exception:  # noqa: BLE001 - fall back to JS click
            driver.execute_script("arguments[0].click();", elem)
        logging.info("Opened 'Download Dataset' section")
    except TimeoutException:
        logging.warning("Could not find a distinct 'Download Dataset' tab; continuing.")


def _candidate_link_elements(driver: Chrome) -> List:
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
    uniq = []
    seen = set()
    for e in elems:
        try:
            key = e.id
        except Exception:  # noqa: BLE001 - fallback
            key = id(e)
        if key not in seen:
            seen.add(key)
            uniq.append(e)
    return uniq


def _click_element(driver: Chrome, el) -> bool:
    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
        time.sleep(0.5)
        el.click()
        return True
    except Exception:  # noqa: BLE001
        pass
    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
        ActionChains(driver).move_to_element(el).pause(0.2).click().perform()
        return True
    except Exception:  # noqa: BLE001
        pass
    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
        driver.execute_script("arguments[0].click();", el)
        return True
    except Exception:  # noqa: BLE001
        return False


def _collect_xlsx_hrefs(driver: Chrome) -> Set[str]:
    hrefs: Set[str] = set()
    for anchor in driver.find_elements(By.XPATH, "//a[contains(@href,'.xlsx') or contains(@href,'.xls')]"):
        try:
            href = anchor.get_attribute("href")
            if href:
                hrefs.add(href)
        except Exception:  # noqa: BLE001
            continue
    return hrefs


def _http_download(url: str, dest_dir: str) -> str:
    local = os.path.join(dest_dir, os.path.basename(url.split("?")[0]))
    headers = {"User-Agent": "Mozilla/5.0"}
    with requests.get(url, stream=True, timeout=90, headers=headers) as response:
        response.raise_for_status()
        with open(local, "wb") as handle:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    handle.write(chunk)
    return local


def attempt_downloads(driver: Chrome) -> Tuple[List[str], Set[str]]:
    clicked_labels: List[str] = []
    discovered: Set[str] = set()

    for el in _candidate_link_elements(driver):
        label = (
            (el.text or "").strip()
            or el.get_attribute("aria-label")
            or el.get_attribute("href")
            or "link"
        )
        if _click_element(driver, el):
            clicked_labels.append(label)
            time.sleep(2)

    discovered |= _collect_xlsx_hrefs(driver)

    iframes = driver.find_elements(By.TAG_NAME, "iframe")
    logging.info("Iframes found: %s", len(iframes))
    for i, frame in enumerate(iframes):
        try:
            driver.switch_to.frame(frame)
        except WebDriverException:
            continue
        try:
            for el in _candidate_link_elements(driver):
                label = (
                    (el.text or "").strip()
                    or el.get_attribute("aria-label")
                    or el.get_attribute("href")
                    or f"iframe[{i}] link"
                )
                if _click_element(driver, el):
                    clicked_labels.append(label)
                    time.sleep(2)
            discovered |= _collect_xlsx_hrefs(driver)
        finally:
            driver.switch_to.default_content()

    logging.info("Clicked labels: %s", clicked_labels)
    logging.info("Discovered direct .xlsx/.xls hrefs: %s", list(discovered))
    return clicked_labels, discovered


def wait_for_downloads(download_dir: str, timeout: int = DOWNLOAD_TIMEOUT_SECS) -> List[str]:
    logging.info("Waiting for downloads to complete...")
    start = time.time()
    while time.time() - start < timeout:
        partials = glob.glob(os.path.join(download_dir, "*.crdownload"))
        if not partials:
            break
        time.sleep(2)
    files = [f for f in glob.glob(os.path.join(download_dir, "*")) if os.path.isfile(f)]
    logging.info("Downloaded files: %s", [os.path.basename(f) for f in files])
    return files


def convert_excels_to_csv(in_paths: List[str], out_dir: str, skip_existing: bool = True) -> List[str]:
    csv_paths: List[str] = []
    for path in in_paths:
        base = os.path.basename(path)
        stem, ext = os.path.splitext(base)
        if ext.lower() in [".xlsx", ".xls"]:
            out_csv = os.path.join(out_dir, f"{stem}.csv")
            
            # Check if CSV already exists
            if skip_existing and os.path.exists(out_csv):
                logging.info("CSV already exists, skipping: %s", os.path.basename(out_csv))
                csv_paths.append(out_csv)
                continue
            
            try:
                df = pd.read_excel(path, engine="openpyxl")
                df.to_csv(out_csv, index=False)
                logging.info("Converted %s -> %s", base, os.path.basename(out_csv))
                csv_paths.append(out_csv)
            except Exception as exc:  # noqa: BLE001
                logging.warning("Failed to convert %s to CSV: %s", base, exc)
    return csv_paths


def cleanup_old_files(output_dir: str, keep_latest_datasets: int = 2) -> None:
    """
    Keep only the latest N datasets (Excel files and their corresponding CSVs).
    Deletes all older files.
    
    Args:
        output_dir: Directory containing Excel and CSV files
        keep_latest_datasets: Number of latest datasets to keep (default: 2 - newest + previous latest)
    """
    if not os.path.exists(output_dir):
        return
    
    # Find all Excel files
    excel_files = list(Path(output_dir).glob("*.xlsx")) + list(Path(output_dir).glob("*.xls"))
    
    if len(excel_files) <= keep_latest_datasets:
        logging.info("Only %d Excel file(s) found, no cleanup needed", len(excel_files))
        return
    
    # Sort Excel files by modification time (newest first)
    excel_files_sorted = sorted(excel_files, key=lambda p: p.stat().st_mtime, reverse=True)
    
    # Keep only the latest N Excel files
    excel_files_to_keep = excel_files_sorted[:keep_latest_datasets]
    
    # Find corresponding CSV files for the Excel files we're keeping
    files_to_keep = set(excel_files_to_keep)
    for excel_file in excel_files_to_keep:
        # Find corresponding CSV (same stem name)
        stem = excel_file.stem
        csv_file = Path(output_dir) / f"{stem}.csv"
        if csv_file.exists():
            files_to_keep.add(csv_file)
    
    # Find all files in directory
    all_excel_files = set(Path(output_dir).glob("*.xlsx")) | set(Path(output_dir).glob("*.xls"))
    all_csv_files = set(Path(output_dir).glob("*.csv"))
    all_files = all_excel_files | all_csv_files
    
    # Files to delete (all files not in files_to_keep)
    files_to_delete = all_files - files_to_keep
    
    deleted_count = 0
    for file_path in files_to_delete:
        try:
            file_path.unlink()
            deleted_count += 1
            logging.info("Deleted old file: %s", file_path.name)
        except Exception as exc:  # noqa: BLE001
            logging.warning("Failed to delete %s: %s", file_path.name, exc)
    
    if deleted_count > 0:
        logging.info("Cleaned up %d old file(s), kept %d latest dataset(s)", deleted_count, len(excel_files_to_keep))
        kept_excel = [f.name for f in excel_files_to_keep]
        logging.info("Kept Excel files: %s", ", ".join(kept_excel))


def main() -> None:
    import argparse
    
    parser = argparse.ArgumentParser(description='Download FDA dashboard data')
    parser.add_argument('--force', action='store_true', help='Force re-download even if CSV already exists')
    args = parser.parse_args()
    
    ensure_dirs()
    
    # Check for existing CSVs to inform user — but proceed to download.
    # The downloader will fetch the latest dataset and then cleanup older files
    # keeping only the newest + previous latest (controlled by cleanup_old_files()).
    existing_csvs = list(Path(OUTPUT_DIR).glob("*.csv"))
    if existing_csvs:
        latest_csv = max(existing_csvs, key=lambda p: p.stat().st_mtime)
        logging.info("Existing CSV found: %s", latest_csv.name)
        print(f"\n✓ Existing CSV found: {latest_csv}")
        print("  Proceeding to download latest datasets; older datasets will be cleaned up (keeps latest 2). Use --force to force re-download behavior if needed.")
    
    driver = chrome_driver(DOWNLOAD_DIR)

    try:
        driver.get(DASHBOARD_URL)
        logging.info("Opened dashboard page")

        open_download_tab(driver)

        clicked_labels, hrefs = attempt_downloads(driver)

        if not clicked_labels:
            logging.warning("No clickable links worked; attempting HTTP downloads for discovered .xlsx URLs.")
        for url in hrefs:
            try:
                saved = _http_download(url, DOWNLOAD_DIR)
                logging.info("HTTP-downloaded: %s", saved)
            except Exception as exc:  # noqa: BLE001
                logging.warning("HTTP download failed for %s: %s", url, exc)

        downloaded = wait_for_downloads(DOWNLOAD_DIR, DOWNLOAD_TIMEOUT_SECS)

        moved: List[str] = []
        for file_path in downloaded:
            dest = os.path.join(OUTPUT_DIR, os.path.basename(file_path))
            try:
                shutil.move(file_path, dest)
            except Exception:  # noqa: BLE001
                shutil.copy2(file_path, dest)
                os.remove(file_path)
            moved.append(dest)

        csvs = convert_excels_to_csv(moved, OUTPUT_DIR, skip_existing=not args.force)

        # Clean up old files - keep only the latest 2 files (newest + previous latest)
        cleanup_old_files(OUTPUT_DIR, keep_latest_datasets=2)

        logging.info("Done.")
        print("\nOutputs:")
        for path in moved:
            print(" - saved:", path)
        for path in csvs:
            print(" - csv  :", path)

    finally:
        try:
            driver.quit()
        except Exception:  # noqa: BLE001
            pass


if __name__ == "__main__":
    main()

