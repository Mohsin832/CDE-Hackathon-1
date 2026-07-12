"""
Smart City AQI - OpenAQ V3 Fetcher
Fetches real air quality reference data for Pakistan from OpenAQ V3 API.
Steps:
  1. Find Pakistan locations
  2. Get sensors for each location
  3. Get latest measurement for each location
Saves everything into data/openaq_readings.csv
"""

import csv
import os
import time
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv

# ---------------------------------------------------------
# 0. LOAD ENV VARIABLES
# ---------------------------------------------------------
load_dotenv()

API_KEY = os.environ.get("OPENAQ_API_KEY")
if not API_KEY:
    raise RuntimeError(
        "OPENAQ_API_KEY not found. Make sure it's set in your .env file."
    )

BASE_URL = "https://api.openaq.org/v3"
HEADERS = {"X-API-Key": API_KEY}

CSV_PATH = os.path.join("data", "openaq_readings.csv")
CSV_HEADERS = [
    "location_id", "station_name", "city", "country_code",
    "latitude", "longitude", "pollutant_type", "pollutant_value",
    "unit", "recorded_at", "source",
]

RATE_LIMIT_SLEEP = 1  # seconds between calls, per spec (60 req/min limit)


# ---------------------------------------------------------
# 1. STEP 0 — LOOK UP PAKISTAN'S NUMERIC COUNTRY ID
# ---------------------------------------------------------
def get_pakistan_country_id() -> int:
    """
    OpenAQ V3's /locations endpoint filters on a numeric countries_id,
    not the ISO code "PK" directly. So we first search /v3/countries
    for the entry whose code == "PK" and grab its numeric id.
    """
    url = f"{BASE_URL}/countries"
    params = {"limit": 300}

    resp = requests.get(url, headers=HEADERS, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    for item in data.get("results", []):
        if item.get("code") == "PK":
            print(f"Pakistan country_id resolved to: {item.get('id')}")
            return item.get("id")

    raise RuntimeError("Could not find Pakistan (code='PK') in /v3/countries results.")


# ---------------------------------------------------------
# 1B. STEP 1 — FIND PAKISTAN LOCATIONS
# ---------------------------------------------------------
def get_pakistan_locations(limit: int = 100) -> list:
    pk_country_id = get_pakistan_country_id()
    time.sleep(RATE_LIMIT_SLEEP)

    url = f"{BASE_URL}/locations"
    params = {"countries_id": pk_country_id, "limit": limit}

    resp = requests.get(url, headers=HEADERS, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    locations = []
    for item in data.get("results", []):
        country = item.get("country") or {}
        # Safety check: only keep results actually tagged as Pakistan
        if country.get("code") != "PK":
            continue

        coords = item.get("coordinates") or {}
        locations.append({
            "location_id": item.get("id"),
            "name": item.get("name"),
            "city": item.get("locality") or item.get("name"),
            "latitude": coords.get("latitude"),
            "longitude": coords.get("longitude"),
        })

    print(f"Found {len(locations)} Pakistan locations.")
    return locations


# ---------------------------------------------------------
# 2. STEP 2 — GET SENSORS FOR A LOCATION
# ---------------------------------------------------------
def get_sensors_for_location(location_id: int) -> list:
    url = f"{BASE_URL}/locations/{location_id}/sensors"
    resp = requests.get(url, headers=HEADERS, timeout=30)

    if resp.status_code != 200:
        print(f"  [WARN] Could not fetch sensors for location {location_id} "
              f"(status {resp.status_code})")
        return []

    data = resp.json()
    sensors = []
    for item in data.get("results", []):
        param = item.get("parameter") or {}
        sensors.append({
            "sensor_id": item.get("id"),
            "parameter_name": param.get("name"),
            "unit": param.get("units"),
        })
    return sensors


# ---------------------------------------------------------
# 3. STEP 3 — GET LATEST MEASUREMENTS FOR A LOCATION
# ---------------------------------------------------------
def get_latest_measurements(location_id: int) -> list:
    url = f"{BASE_URL}/locations/{location_id}/latest"
    resp = requests.get(url, headers=HEADERS, timeout=30)

    if resp.status_code != 200:
        print(f"  [WARN] Could not fetch latest data for location {location_id} "
              f"(status {resp.status_code})")
        return []

    data = resp.json()
    return data.get("results", [])


# ---------------------------------------------------------
# 4. MAP API RESPONSE -> SNOWFLAKE SCHEMA FIELDS
# ---------------------------------------------------------
def build_rows_for_location(location: dict, sensors: list, latest_results: list) -> list:
    """
    Combine sensor metadata (parameter name/unit) with the latest
    measurement values, and map into our Snowflake column names.
    Only keep pm25 / pm10 / co2 parameters (per spec + ETL filter later).
    """
    # Build a lookup: sensor_id -> {parameter_name, unit}
    sensor_lookup = {s["sensor_id"]: s for s in sensors}

    rows = []
    for measurement in latest_results:
        sensor_id = measurement.get("sensorsId") or measurement.get("sensorId")
        sensor_meta = sensor_lookup.get(sensor_id, {})
        parameter_name = sensor_meta.get("parameter_name", "unknown")
        unit = sensor_meta.get("unit", "unknown")

        value = measurement.get("value")
        datetime_info = measurement.get("datetime") or {}
        recorded_at = datetime_info.get("utc") if isinstance(datetime_info, dict) else datetime_info

        if value is None:
            continue

        rows.append({
            "location_id": location["location_id"],
            "station_name": location["name"],
            "city": location["city"],
            "country_code": "PK",
            "latitude": location["latitude"],
            "longitude": location["longitude"],
            "pollutant_type": parameter_name,
            "pollutant_value": value,
            "unit": unit,
            "recorded_at": recorded_at or datetime.now(timezone.utc).isoformat(),
            "source": "openaq_v3",
        })

    return rows


# ---------------------------------------------------------
# 5. CSV WRITER
# ---------------------------------------------------------
def ensure_csv_exists():
    os.makedirs("data", exist_ok=True)
    if not os.path.exists(CSV_PATH):
        with open(CSV_PATH, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
            writer.writeheader()


def save_rows_to_csv(rows: list):
    if not rows:
        return
    with open(CSV_PATH, mode="a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
        for r in rows:
            writer.writerow(r)


# ---------------------------------------------------------
# 6. MAIN
# ---------------------------------------------------------
def run_fetcher():
    ensure_csv_exists()
    print("Fetching OpenAQ data for Pakistan...\n")

    locations = get_pakistan_locations()
    time.sleep(RATE_LIMIT_SLEEP)

    if not locations:
        print("No Pakistan locations found. Nothing to fetch — check your API key "
              "or try again later (OpenAQ coverage in Pakistan is limited).")
        return

    total_rows_saved = 0

    for loc in locations:
        loc_id = loc["location_id"]
        print(f"Processing location {loc_id} - {loc['name']} ({loc['city']})")

        sensors = get_sensors_for_location(loc_id)
        time.sleep(RATE_LIMIT_SLEEP)

        latest = get_latest_measurements(loc_id)
        time.sleep(RATE_LIMIT_SLEEP)

        rows = build_rows_for_location(loc, sensors, latest)
        save_rows_to_csv(rows)
        total_rows_saved += len(rows)

        print(f"  -> saved {len(rows)} readings")

    print(f"\nDone. Total OpenAQ readings saved: {total_rows_saved}")
    print(f"CSV location: {CSV_PATH}")


if __name__ == "__main__":
    run_fetcher()
