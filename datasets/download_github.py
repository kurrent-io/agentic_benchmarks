"""Download GitHub Archive data sample.

Source: https://www.gharchive.org/
License: Open

GitHub Archive provides hourly dumps of all public GitHub events.
Files are ~50-100MB per hour compressed.

This script downloads a configurable sample (default: 1 day).
"""

import gzip
import json
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent / "github"


def download(
    start_date: str = "2024-01-15",
    hours: int = 24,
    max_events_per_hour: int = 10000
):
    """Download GitHub Archive sample.

    Args:
        start_date: Start date in YYYY-MM-DD format
        hours: Number of hours to download
        max_events_per_hour: Limit events per hour (None for all)
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    output_file = OUTPUT_DIR / f"events_{start_date}_{hours}h.jsonl"

    if output_file.exists():
        print(f"Sample already exists: {output_file}")
        return output_file

    start = datetime.strptime(start_date, "%Y-%m-%d")
    all_events = []

    for i in range(hours):
        dt = start + timedelta(hours=i)
        url = f"https://data.gharchive.org/{dt.strftime('%Y-%m-%d')}-{dt.hour}.json.gz"

        print(f"Fetching {url}...")
        try:
            response = urllib.request.urlopen(url, timeout=30)
            data = gzip.decompress(response.read())

            events = []
            for line in data.decode('utf-8').strip().split('\n'):
                if line:
                    events.append(json.loads(line))
                    if max_events_per_hour and len(events) >= max_events_per_hour:
                        break

            all_events.extend(events)
            print(f"  Got {len(events)} events")

        except Exception as e:
            print(f"  Error: {e}")
            continue

    # Write to JSONL file
    print(f"Writing {len(all_events)} events to {output_file}...")
    with open(output_file, 'w') as f:
        for event in all_events:
            f.write(json.dumps(event) + '\n')

    print(f"Downloaded {len(all_events)} events to {output_file}")
    return output_file


def list_event_types(filepath: Path = None):
    """List event types in downloaded data."""
    filepath = filepath or next(OUTPUT_DIR.glob("*.jsonl"), None)
    if not filepath:
        print("No data file found. Run download() first.")
        return

    from collections import Counter
    types = Counter()

    with open(filepath) as f:
        for line in f:
            event = json.loads(line)
            types[event.get("type", "unknown")] += 1

    print("Event types:")
    for event_type, count in types.most_common():
        print(f"  {event_type}: {count}")


if __name__ == "__main__":
    # Download 1 day sample with 10k events/hour limit (~240k events)
    download(start_date="2024-01-15", hours=24, max_events_per_hour=10000)
    list_event_types()
