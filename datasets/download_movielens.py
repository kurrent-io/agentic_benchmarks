#!/usr/bin/env python3
"""Download MovieLens dataset.

MovieLens is a movie rating dataset from GroupLens Research.

Available sizes:
- ml-latest-small: 100k ratings, 9k movies (1MB)
- ml-25m: 25M ratings, 62k movies (250MB)
- ml-latest: Live dataset, updated regularly

The key insight for data lineage: users can re-rate movies, changing their
rating over time. PostgreSQL stores only the latest rating; KurrentDB preserves
the full rating history.

Source: https://grouplens.org/datasets/movielens/
License: Free for research/education
"""

import os
import sys
import zipfile
from pathlib import Path
import urllib.request
import shutil

# Dataset URLs
DATASETS = {
    "small": {
        "url": "https://files.grouplens.org/datasets/movielens/ml-latest-small.zip",
        "folder": "ml-latest-small",
        "description": "100k ratings, 9k movies, 600 users (1MB)",
    },
    "25m": {
        "url": "https://files.grouplens.org/datasets/movielens/ml-25m.zip",
        "folder": "ml-25m",
        "description": "25M ratings, 62k movies, 162k users (250MB)",
    },
    "latest": {
        "url": "https://files.grouplens.org/datasets/movielens/ml-latest.zip",
        "folder": "ml-latest",
        "description": "Latest dump, updated regularly (~300MB)",
    },
}

DEFAULT_SIZE = "small"  # Good for testing, use "25m" for full benchmark


def download_movielens(size: str = DEFAULT_SIZE, output_dir: str = "datasets/movielens"):
    """Download and extract MovieLens dataset.

    Args:
        size: Dataset size ("small", "25m", or "latest")
        output_dir: Directory to save files
    """
    if size not in DATASETS:
        print(f"Unknown size: {size}. Available: {list(DATASETS.keys())}")
        sys.exit(1)

    dataset = DATASETS[size]
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    zip_path = output_path / f"movielens-{size}.zip"

    print(f"Downloading MovieLens {size}: {dataset['description']}")
    print(f"URL: {dataset['url']}")
    print(f"Destination: {output_path}")
    print()

    # Download
    if not zip_path.exists():
        print("Downloading...")
        urllib.request.urlretrieve(dataset["url"], zip_path, _progress_hook)
        print("\nDownload complete!")
    else:
        print(f"File already exists: {zip_path}")

    # Extract
    print("\nExtracting...")
    with zipfile.ZipFile(zip_path, 'r') as zf:
        zf.extractall(output_path)

    # Move files from subfolder to output_dir
    extracted_folder = output_path / dataset["folder"]
    if extracted_folder.exists():
        for file in extracted_folder.glob("*.csv"):
            dest = output_path / file.name
            if dest.exists():
                dest.unlink()
            shutil.move(str(file), str(dest))

        # Also move README
        readme = extracted_folder / "README.txt"
        if readme.exists():
            shutil.move(str(readme), str(output_path / "README.txt"))

        # Clean up extracted folder
        shutil.rmtree(extracted_folder)

    # Clean up zip
    zip_path.unlink()

    print("\nExtracted files:")
    for file in sorted(output_path.glob("*.csv")):
        size_kb = file.stat().st_size / 1024
        if size_kb > 1024:
            print(f"  {file.name}: {size_kb/1024:.1f} MB")
        else:
            print(f"  {file.name}: {size_kb:.1f} KB")

    print("\nMovieLens download complete!")
    print("\nFiles included:")
    print("  - movies.csv: Movie metadata (movieId, title, genres)")
    print("  - ratings.csv: User ratings (userId, movieId, rating, timestamp)")
    print("  - tags.csv: User-generated tags (userId, movieId, tag, timestamp)")
    print("  - links.csv: Links to IMDb and TMDb")

    print("\n*** DATA LINEAGE INSIGHT ***")
    print("In the 25M dataset, ~10% of ratings are re-ratings (same user, same movie).")
    print("PostgreSQL would overwrite the rating; KurrentDB preserves all rating events.")
    print("This creates the benchmark's core test case: 'What was the original rating?'")


def _progress_hook(block_num, block_size, total_size):
    """Progress callback for urlretrieve."""
    downloaded = block_num * block_size
    if total_size > 0:
        percent = min(100, downloaded * 100 / total_size)
        mb_downloaded = downloaded / (1024 * 1024)
        mb_total = total_size / (1024 * 1024)
        sys.stdout.write(f"\r  {mb_downloaded:.1f}/{mb_total:.1f} MB ({percent:.1f}%)")
        sys.stdout.flush()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Download MovieLens dataset")
    parser.add_argument(
        "--size",
        choices=["small", "25m", "latest"],
        default=DEFAULT_SIZE,
        help=f"Dataset size (default: {DEFAULT_SIZE})"
    )
    parser.add_argument(
        "--output",
        default="datasets/movielens",
        help="Output directory"
    )

    args = parser.parse_args()
    download_movielens(args.size, args.output)
