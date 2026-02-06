"""Download BTS Airline On-Time Performance data.

Source: https://www.transtats.bts.gov/DL_SelectFields.aspx?gnoession_VQ=FGJ
License: US Government Public Domain

Data includes: departure/arrival times, delays, cancellations, diversions.
~500MB per year, 6M+ flights.
"""

import urllib.request
import zipfile
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent / "bts"

# Pre-downloaded samples are available from various mirrors
# This uses the Bureau of Transportation Statistics direct download
# Note: The BTS website requires form submission, so we use a mirror

SAMPLE_URLS = {
    # Smaller sample for testing (1 month)
    "2024_01": "https://transtats.bts.gov/PREZIP/On_Time_Reporting_Carrier_On_Time_Performance_1987_present_2024_1.zip",
}


def download(year: int = 2024, month: int = 1):
    """Download BTS airline data for specified month.

    Note: Direct download requires accepting terms on BTS website.
    For automated download, use the Kaggle mirror or manual download.

    Args:
        year: Year (2000-present)
        month: Month (1-12)
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    output_file = OUTPUT_DIR / f"flights_{year}_{month:02d}.csv"

    if output_file.exists():
        print(f"BTS data already exists: {output_file}")
        return output_file

    print(f"""
BTS Airline Data Download Instructions:

1. Visit: https://www.transtats.bts.gov/DL_SelectFields.aspx?gnoession_VQ=FGJ

2. Select fields:
   - FlightDate, Reporting_Airline, Flight_Number_Reporting_Airline
   - Origin, Dest, CRSDepTime, DepTime, DepDelay
   - CRSArrTime, ArrTime, ArrDelay
   - Cancelled, CancellationCode, Diverted
   - ActualElapsedTime, Distance

3. Download and extract to: {OUTPUT_DIR}

4. Rename to: {output_file.name}

Alternative: Use Kaggle dataset
    kaggle datasets download -d yuanyuwendymu/airline-delay-and-cancellation-data-2009-2018
""")

    return None


def download_sample():
    """Download a small sample for testing."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Create a synthetic sample for testing
    sample_file = OUTPUT_DIR / "flights_sample.csv"

    if sample_file.exists():
        print(f"Sample already exists: {sample_file}")
        return sample_file

    print("Creating synthetic sample for testing...")

    import random
    from datetime import date, timedelta

    carriers = ["AA", "UA", "DL", "WN", "AS", "B6"]
    airports = ["LAX", "JFK", "ORD", "DFW", "ATL", "SFO", "SEA", "MIA"]

    with open(sample_file, 'w') as f:
        # Header
        f.write("FL_DATE,CARRIER,FL_NUM,ORIGIN,DEST,CRS_DEP_TIME,DEP_TIME,DEP_DELAY,")
        f.write("CRS_ARR_TIME,ARR_TIME,ARR_DELAY,CANCELLED,DIVERTED,DISTANCE\n")

        base_date = date(2024, 1, 1)

        for i in range(10000):  # 10k flights
            fl_date = base_date + timedelta(days=random.randint(0, 30))
            carrier = random.choice(carriers)
            fl_num = random.randint(100, 9999)
            origin = random.choice(airports)
            dest = random.choice([a for a in airports if a != origin])

            crs_dep = random.randint(600, 2200)
            dep_delay = random.choices(
                [0, random.randint(-10, 10), random.randint(15, 60), random.randint(60, 180)],
                weights=[0.3, 0.4, 0.2, 0.1]
            )[0]

            cancelled = random.random() < 0.02  # 2% cancelled
            diverted = not cancelled and random.random() < 0.005  # 0.5% diverted

            if cancelled:
                dep_time = ""
                arr_time = ""
                arr_delay = ""
            else:
                dep_time = crs_dep + dep_delay
                flight_time = random.randint(60, 360)
                crs_arr = crs_dep + flight_time
                arr_delay = dep_delay + random.randint(-15, 15)
                arr_time = crs_arr + arr_delay

            distance = random.randint(200, 3000)

            f.write(f"{fl_date},{carrier},{fl_num},{origin},{dest},{crs_dep},")
            f.write(f"{dep_time if not cancelled else ''},{dep_delay if not cancelled else ''},")
            f.write(f"{crs_arr if not cancelled else ''},{arr_time if not cancelled else ''},")
            f.write(f"{arr_delay if not cancelled else ''},{1 if cancelled else 0},")
            f.write(f"{1 if diverted else 0},{distance}\n")

    print(f"Created sample: {sample_file}")
    return sample_file


if __name__ == "__main__":
    # Try to download, or create sample
    result = download()
    if not result:
        download_sample()
