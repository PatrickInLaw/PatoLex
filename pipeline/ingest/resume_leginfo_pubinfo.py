#!/usr/bin/env python3
import os
import sys
import zipfile
import datetime
import requests
from pathlib import Path
import config

SCRATCH = Path(config.path_for("data_root"))
LOG_FILE = SCRATCH / "leginfo-resume-run.log"
BASE_URL = "https://downloads.leginfo.legislature.ca.gov/pubinfo_{}.zip"

# Only the remaining 4 years
REMAINING_YEARS = [2017, 2019, 2021, 2023]

def log(phase, desc, status="OK"):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M PT")
    line = f"[{ts}] {phase} | {desc} | {status}\n"
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line)
    print(line.strip())

def main():
    log("INIT", f"resume_leginfo_pubinfo.py starting (4 remaining years: 2017, 2019, 2021, 2023)")
    log("INIT", f"Scratch dir: {SCRATCH}")
    
    success_count = 0
    skip_count = 0
    fail_count = 0
    
    for year in REMAINING_YEARS:
        dest_dir = SCRATCH / f"pubinfo_{year}"
        if dest_dir.exists():
            log("SKIP", f"pubinfo_{year} already present", "OK")
            skip_count += 1
            continue
        
        url = BASE_URL.format(year)
        zip_path = SCRATCH / f"pubinfo_{year}.zip"
        
        log("DOWNLOAD", f"Fetching pubinfo_{year}.zip (timeout: 600s)")
        try:
            r = requests.get(url, stream=True, timeout=600)
            r.raise_for_status()
            total = int(r.headers.get("content-length", 0))
            
            downloaded = 0
            with open(zip_path, "wb") as f:
                for chunk in r.iter_content(65536):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total > 0 and downloaded % (50*1024*1024) == 0:
                            pct = (downloaded / total) * 100
                            log("DOWNLOAD", f"pubinfo_{year}: {pct:.1f}% ({downloaded/1024/1024:.1f}MB / {total/1024/1024:.1f}MB)")
            
            size_mb = downloaded / 1024 / 1024
            log("DOWNLOAD", f"pubinfo_{year}.zip downloaded: {size_mb:.1f} MB", "OK")
            
            log("EXTRACT", f"Extracting pubinfo_{year}.zip")
            dest_dir.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(zip_path, "r") as z:
                z.extractall(dest_dir)
            
            zip_path.unlink()
            
            log("EXTRACT", f"pubinfo_{year} extracted successfully", "OK")
            success_count += 1
            
        except requests.exceptions.Timeout:
            log("ERROR", f"pubinfo_{year}: timeout (600s exceeded)", "FAIL")
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
