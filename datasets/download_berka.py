"""Download Berka Czech Banking dataset.

Source: https://data.world/lpetrocelli/czech-financial-dataset-real-anonymized-transactions
Alternative: https://sorry.vse.cz/~berka/challenge/pkdd1999/

License: Academic use
"""

import urllib.request
import zipfile
from pathlib import Path

# Using the relational dataset version
BASE_URL = "https://sorry.vse.cz/~berka/challenge/pkdd1999"
FILES = [
    "data.zip",  # Contains all CSVs
]

OUTPUT_DIR = Path(__file__).parent / "berka"


def download():
    """Download and extract Berka dataset."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Check if already downloaded
    if (OUTPUT_DIR / "trans.asc").exists():
        print(f"Berka dataset already exists in {OUTPUT_DIR}")
        return

    print("Downloading Berka dataset...")

    zip_path = OUTPUT_DIR / "data.zip"

    # Download
    url = f"{BASE_URL}/data.zip"
    print(f"Fetching {url}...")
    urllib.request.urlretrieve(url, zip_path)

    # Extract
    print("Extracting...")
    with zipfile.ZipFile(zip_path, 'r') as zf:
        zf.extractall(OUTPUT_DIR)

    zip_path.unlink()  # Remove zip
    print(f"Downloaded to {OUTPUT_DIR}")


def list_files():
    """List downloaded files."""
    if not OUTPUT_DIR.exists():
        print("Dataset not downloaded yet. Run download() first.")
        return []

    # Berka uses .asc extension for data files
    files = list(OUTPUT_DIR.glob("*.asc")) + list(OUTPUT_DIR.glob("*.csv"))
    print(f"Files in {OUTPUT_DIR}:")
    for f in files:
        size_kb = f.stat().st_size / 1024
        print(f"  {f.name}: {size_kb:.1f} KB")
    return files


if __name__ == "__main__":
    download()
    list_files()
