"""Download Olist Brazilian E-Commerce dataset from Kaggle.

Source: https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce
License: CC BY-NC-SA 4.0

Requires: kaggle CLI configured with API token
    pip install kaggle
    Configure ~/.kaggle/kaggle.json
"""

import os
import subprocess
import zipfile
from pathlib import Path

DATASET = "olistbr/brazilian-ecommerce"
OUTPUT_DIR = Path(__file__).parent / "olist"


def download():
    """Download and extract Olist dataset."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Check if already downloaded
    if (OUTPUT_DIR / "olist_orders_dataset.csv").exists():
        print(f"Olist dataset already exists in {OUTPUT_DIR}")
        return

    print(f"Downloading {DATASET}...")

    # Download via Kaggle CLI
    try:
        subprocess.run([
            "kaggle", "datasets", "download",
            "-d", DATASET,
            "-p", str(OUTPUT_DIR),
            "--unzip"
        ], check=True)
        print(f"Downloaded to {OUTPUT_DIR}")
    except FileNotFoundError:
        print("ERROR: kaggle CLI not found. Install with: pip install kaggle")
        print("Then configure: https://www.kaggle.com/docs/api")
        raise
    except subprocess.CalledProcessError as e:
        print(f"ERROR: Download failed: {e}")
        raise


def list_files():
    """List downloaded files."""
    if not OUTPUT_DIR.exists():
        print("Dataset not downloaded yet. Run download() first.")
        return []

    files = list(OUTPUT_DIR.glob("*.csv"))
    print(f"Files in {OUTPUT_DIR}:")
    for f in files:
        size_mb = f.stat().st_size / (1024 * 1024)
        print(f"  {f.name}: {size_mb:.1f} MB")
    return files


if __name__ == "__main__":
    download()
    list_files()
