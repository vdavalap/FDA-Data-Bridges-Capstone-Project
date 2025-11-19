# FDA Data Dashboard Excel Download Guide

This guide explains how to download Excel files from the [FDA Data Dashboard](https://datadashboard.fda.gov/oii/cd/#).

## Quick Start

### Method 1: Using Predefined Dashboard Type

```bash
python download_excel_fda.py --dashboard-type compliance --auto-find
```

Available dashboard types:
- `compliance` - Main compliance dashboard
- `inspections` - Inspections data
- `compliance-actions` - Compliance actions
- `recalls` - Recalls data
- `imports` - Imports data

### Method 2: Direct Dashboard URL

```bash
python download_excel_fda.py --dashboard "https://datadashboard.fda.gov/oii/cd/#" --auto-find
```

### Method 3: Direct Excel File URL

If you know the direct URL to the Excel file:

```bash
python download_excel_fda.py --url "https://datadashboard.fda.gov/oii/cd/api/export/inspections.xlsx"
```

## Understanding the FDA Data Dashboard

The FDA Data Dashboard at [datadashboard.fda.gov/oii/cd/#](https://datadashboard.fda.gov/oii/cd/#) is a JavaScript-based application that provides access to:

- **Inspections**: U.S. domestic and foreign inspections by fiscal year, classification, product type
- **Compliance Actions**: Warning letters, injunctions and seizures
- **Recalls**: Recalls by fiscal year, classification, product type, status
- **Imports Summary**: Imports summary data by fiscal year
- **Import Refusals**: Import refusals by fiscal year, product categories, country
- **Imports Entry**: Imports entry data by fiscal year

## Finding the Download URL

Since the dashboard uses JavaScript, you may need to:

1. **Open the dashboard in your browser**
2. **Open Developer Tools** (F12)
3. **Navigate to the Network tab**
4. **Apply filters or select data you want**
5. **Click the export/download button**
6. **Look for the API call** in the Network tab that downloads the Excel file
7. **Copy the request URL** and use it with `--url`

## Example: Finding Export API Endpoint

1. Open https://datadashboard.fda.gov/oii/cd/#/inspections
2. Open browser Developer Tools (F12)
3. Go to Network tab
4. Filter by "XHR" or "Fetch"
5. Apply filters on the dashboard (e.g., select fiscal year, product type)
6. Click "Export" or "Download" button
7. Find the API call (might look like `/api/inspections/export` or similar)
8. Copy the full URL and use it:

```bash
python download_excel_fda.py --url "https://datadashboard.fda.gov/oii/cd/api/inspections/export?fiscalYear=2024&format=xlsx"
```

## Troubleshooting

### "No Excel download links found"

The dashboard requires JavaScript interaction. Try:

1. **Manual Method**: Open the dashboard, configure your filters, and download manually
2. **Find API Endpoint**: Use browser developer tools to find the export API endpoint
3. **Use Selenium** (advanced): For fully automated downloads, you may need to use Selenium to interact with the JavaScript

### "Dashboard may require JavaScript interaction"

The script detected that the dashboard uses JavaScript. Options:

1. Use browser developer tools to find the direct API endpoint
2. Consider using Selenium for full automation (requires additional setup)
3. Download manually and use the script for direct URLs

## Advanced: Using Selenium (Optional)

For fully automated downloads from JavaScript-heavy dashboards, you can extend the script with Selenium:

```python
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# This would require additional implementation
```

## Data Refresh Schedule

According to the FDA:
- **Imports Entry**: Refreshed every Thursday night
- **Other dashboards**: Refreshed every Monday
- **Imports Summary**: Published annually in October
- **Shipment Details**: Posted by the 5th of each month

## References

- [FDA Data Dashboard](https://datadashboard.fda.gov/oii/cd/#)
- [FDA Compliance Program Manual](https://www.fda.gov/inspections-compliance-enforcement-and-criminal-investigations/compliance-program-manual)

