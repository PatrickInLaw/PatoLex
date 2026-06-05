#!/usr/bin/env python3
"""
acquire_leginfo_pubinfo.py - Download missing leginfo PUBINFO archives.

Downloads pubinfo_YYYY.zip for each missing year, extracts to PatoLex-scratch/pubinfo_YYYY/.
Skips years already present. Logs to docs/80_PROJECT_HISTORY/run-logs/acquire-leginfo-pubinfo-run.log.
"""

import os
import sys
import zipfile
import datetime
import requests
from pathlib import Path

SCRATCH = Path(r"C:\Users\PatrickKolasinski\PatoLex-scratch")
REPO_ROOT = Path(r"C:\Users\PatrickKolasinski\Documents\GitHub\PatoLex")
LOG_FILE = REPO_ROOT / "docs" / "80_PROJECT_HISTORY" / "run-logs" / "acquire-leginfo-pubinfo-run.log"
BASE_URL = "https://downloads.leginfo.legislature.ca.gov/pubinfo_{}.zip"

# Years that need to be downloaded (already present: 1989, 1993, 2001, 2003, 2025)
MISSING_YEARS = [1991, 1995, 1997, 1999, 2005, 2007, 2009, 2011, 2013, 2015, 2017, 2019, 2021, 2023]

def log(phase, desc, status="OK"):
    """Log a line to the run log file."""
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M PT")
    line = f"[{ts}] {phase} | {desc} | {status}\n"
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line)
    print(line.strip())

def main():
    log("INIT", f"acquire_leginfo_pubinfo.py starting")
    log("INIT", f"Scratch dir: {SCRATCH}")
    log("INIT", f"Target years: {len(MISSING_YEARS)} (1991, 1995, 1997, 1999, 2005, 2007, 2009, 2011, 2013, 2015, 2017, 2019, 2021, 2023)")
    
    success_count = 0
    skip_count = 0
    fail_count = 0
    
    for year in MISSING_YEARS:
        dest_dir = SCRATCH / f"pubinfo_{year}"
        if dest_dir.exists():
            log("SKIP", f"pubinfo_{year} already present", "OK")
            skip_count += 1
            continue
        
        url = BASE_URL.format(year)
        zip_path = SCRATCH / f"pubinfo_{year}.zip"
        
        log("DOWNLOAD", f"Fetching pubinfo_{year}.zip from {url}")
        try:
            # Download with timeout and streaming
            r = requests.get(url, stream=True, timeout=120)
            r.raise_for_status()
            total = int(r.headers.get("content-length", 0))
            
            downloaded = 0
            with open(zip_path, "wb") as f:
                for chunk in r.iter_content(65536):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
            
            size_mb = downloaded / 1024 / 1024
            log("DOWNLOAD", f"pubinfo_{year}.zip downloaded: {size_mb:.1f} MB", "OK")
            
            # Extract
            log("EXTRACT", f"Extracting pubinfo_{year}.zip to {dest_dir}")
            dest_dir.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(zip_path, "r") as z:
                z.extractall(dest_dir)
            
            # Remove zip
            zip_path.unlink()
            
            log("EXTRACT", f"pubinfo_{year} extracted successfully", "OK")
            success_count += 1
            
        except requests.exceptions.Timeout:
            log("ERROR", f"pubinfo_{year}: timeout (120s exceeded)", "FAIL")
            fail_count += 1
        except requests.exceptions.HTTPError as e:
            log("ERROR", f"pubinfo_{year}: HTTP {e.response.status_code}", "FAIL")
            fail_count += 1
        except Exception as e:
            log("ERROR", f"pubinfo_{year}: {type(e).__name__}: {e}", "FAIL")
            fail_count += 1
    
    log("SUMMARY", f"Complete: {success_count} downloaded, {skip_count} skipped, {fail_count} failed", "OK" if fail_count == 0 else "WARN")

if __name__ == "__main__":
    main()
