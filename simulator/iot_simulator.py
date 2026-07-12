"""
Smart City AQI - IoT Sensor Simulator
Simulates 10 air quality sensors across 5 Pakistani cities.
Generates one reading per sensor every 10 seconds.
Saves to CSV. (Snowflake insert will be added later.)
"""

import csv
import math
import os
import random
import time
from datetime import datetime, timezone

# ---------------------------------------------------------
# 1. SENSOR NETWORK CONFIG
# ---------------------------------------------------------
SENSORS = [
    {"sensor_id": "PKS_KHI_IND_01", "city": "Karachi",   "zone_type": "industrial"},
    {"sensor_id": "PKS_KHI_TRF_02", "city": "Karachi",   "zone_type": "traffic"},
    {"sensor_id": "PKS_LHR_RES_01", "city": "Lahore",    "zone_type": "residential"},
    {"sensor_id": "PKS_LHR_IND_02", "city": "Lahore",    "zone_type": "industrial"},
    {"sensor_id": "PKS_ISB_PRK_01", "city": "Islamabad", "zone_type": "park"},
    {"sensor_id": "PKS_ISB_TRF_02", "city": "Islamabad", "zone_type": "traffic"},
    {"sensor_id": "PKS_PEW_IND_01", "city": "Peshawar",  "zone_type": "industrial"},
    {"sensor_id": "PKS_PEW_RES_02", "city": "Peshawar",  "zone_type": "residential"},
    {"sensor_id": "PKS_MUL_TRF_01", "city": "Multan",    "zone_type": "traffic"},
    {"sensor_id": "PKS_MUL_PRK_02", "city": "Multan",    "zone_type": "park"},
]

# ---------------------------------------------------------
# 2. ZONE BASE VALUES (min, max) per zone type
# ---------------------------------------------------------
ZONE_BASE = {
    "industrial":  {"pm25": (80, 120), "co2": (600, 900), "temp": (30, 42)},
    "traffic":     {"pm25": (55, 80),  "co2": (500, 700), "temp": (28, 40)},
    "residential": {"pm25": (25, 50),  "co2": (420, 500), "temp": (25, 38)},
    "park":        {"pm25": (8, 20),   "co2": (400, 430), "temp": (22, 35)},
}

CSV_PATH = os.path.join("data", "iot_readings.csv")
CSV_HEADERS = [
    "sensor_id", "city", "zone_type", "pm25", "pm10", "co2_ppm",
    "temperature_c", "humidity_pct", "wind_speed_kmh",
    "aqi_value", "severity", "recorded_at",
]


# ---------------------------------------------------------
# 3. AQI CALCULATION (EPA STANDARD BREAKPOINTS)
# ---------------------------------------------------------
AQI_BREAKPOINTS = [
    # (pm_lo, pm_hi, aqi_lo, aqi_hi, severity_label)
    (0.0, 12.0, 0, 50, "GOOD"),
    (12.1, 35.4, 51, 100, "MODERATE"),
    (35.5, 55.4, 101, 150, "UNHEALTHY FOR SENSITIVE"),
    (55.5, 150.4, 151, 200, "UNHEALTHY"),
    (150.5, 250.4, 201, 300, "VERY UNHEALTHY"),
    (250.5, 500.4, 301, 500, "HAZARDOUS"),
]


def calculate_aqi(pm25: float):
    """Return (aqi_value, severity_label) using EPA breakpoint formula."""
    # Clamp pm25 into valid range
    pm25 = max(0.0, min(pm25, 500.4))

    for pm_lo, pm_hi, aqi_lo, aqi_hi, severity in AQI_BREAKPOINTS:
        if pm_lo <= pm25 <= pm_hi:
            aqi = ((aqi_hi - aqi_lo) / (pm_hi - pm_lo)) * (pm25 - pm_lo) + aqi_lo
            return round(aqi, 1), severity

    # Fallback (shouldn't happen since we clamp above)
    return 500.0, "HAZARDOUS"


def simplified_severity(severity_label: str) -> str:
    """
    Map the 6 EPA labels down to the 4 labels the spec's `severity`
    field expects: GOOD / MODERATE / UNHEALTHY / HAZARDOUS
    """
    mapping = {
        "GOOD": "GOOD",
        "MODERATE": "MODERATE",
        "UNHEALTHY FOR SENSITIVE": "UNHEALTHY",
        "UNHEALTHY": "UNHEALTHY",
        "VERY UNHEALTHY": "HAZARDOUS",
        "HAZARDOUS": "HAZARDOUS",
    }
    return mapping.get(severity_label, "MODERATE")


# ---------------------------------------------------------
# 4. READING GENERATION
# ---------------------------------------------------------
def time_of_day_factor(hour: int) -> float:
    """Peaks at 8am and 6pm, per spec formula."""
    return 1.0 + 0.3 * math.sin((hour - 8) * math.pi / 12)


def add_noise(value: float, pct: float = 0.15) -> float:
    """Add +/- pct random noise to a value."""
    noise = random.uniform(-pct, pct)
    return value * (1 + noise)


def generate_reading(sensor: dict) -> dict:
    zone = sensor["zone_type"]
    base = ZONE_BASE[zone]
    now = datetime.now(timezone.utc)
    hour = now.hour

    tod_factor = time_of_day_factor(hour)

    # Base values with time-of-day effect
    pm25_base = random.uniform(*base["pm25"]) * tod_factor
    co2_base = random.uniform(*base["co2"]) * tod_factor
    temp_base = random.uniform(*base["temp"])

    # Apply +/-15% noise
    pm25 = add_noise(pm25_base)
    co2_ppm = add_noise(co2_base)
    temperature_c = add_noise(temp_base)

    # 15% chance of anomaly spike on pm25
    if random.random() < 0.15:
        pm25 *= random.uniform(2.5, 4.0)

    # Clamp pm25 to spec range [0, 500]
    pm25 = max(0.0, min(pm25, 500.0))

    # pm10 must always be >= pm25
    pm10 = pm25 + random.uniform(5, 50)
    pm10 = max(pm25, min(pm10, 600.0))

    # Clamp remaining fields to spec ranges
    co2_ppm = max(400.0, min(co2_ppm, 2000.0))
    temperature_c = max(15.0, min(temperature_c, 45.0))
    humidity_pct = random.uniform(10, 90)
    wind_speed_kmh = random.uniform(0, 60)

    aqi_value, epa_severity = calculate_aqi(pm25)
    severity = simplified_severity(epa_severity)

    return {
        "sensor_id": sensor["sensor_id"],
        "city": sensor["city"],
        "zone_type": zone,
        "pm25": round(pm25, 2),
        "pm10": round(pm10, 2),
        "co2_ppm": round(co2_ppm, 2),
        "temperature_c": round(temperature_c, 2),
        "humidity_pct": round(humidity_pct, 2),
        "wind_speed_kmh": round(wind_speed_kmh, 2),
        "aqi_value": aqi_value,
        "severity": severity,
        "recorded_at": now.isoformat(),
    }


# ---------------------------------------------------------
# 5. CSV WRITER
# ---------------------------------------------------------
def ensure_csv_exists():
    os.makedirs("data", exist_ok=True)
    if not os.path.exists(CSV_PATH):
        with open(CSV_PATH, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
            writer.writeheader()


def save_readings_to_csv(readings: list):
    with open(CSV_PATH, mode="a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
        for r in readings:
            writer.writerow(r)


# ---------------------------------------------------------
# 6. MAIN LOOP
# ---------------------------------------------------------
def run_simulator(duration_minutes: int = 30, interval_seconds: int = 10):
    ensure_csv_exists()
    print(f"Starting IoT simulator for {duration_minutes} minutes...")
    print(f"Saving readings to: {CSV_PATH}\n")

    end_time = time.time() + duration_minutes * 60
    batch_count = 0

    while time.time() < end_time:
        batch_count += 1
        readings = [generate_reading(sensor) for sensor in SENSORS]

        save_readings_to_csv(readings)

        for r in readings:
            if r["severity"] in ("UNHEALTHY", "HAZARDOUS"):
                print(
                    f"[ALERT] {r['recorded_at']} | {r['sensor_id']} ({r['city']}) "
                    f"| PM2.5={r['pm25']} | AQI={r['aqi_value']} | {r['severity']}"
                )

        print(f"Batch {batch_count} saved -> {len(readings)} readings "
              f"@ {datetime.now(timezone.utc).isoformat()}")

        time.sleep(interval_seconds)

    print("\nSimulator finished.")


if __name__ == "__main__":
    # Change duration_minutes=30 for the real hackathon run.
    # Use a smaller number (e.g. 1) first just to test it works.
    run_simulator(duration_minutes=1, interval_seconds=10)


    
