"""
Smart City AQI - ETL Pipeline
1. Load IoT + OpenAQ CSVs
2. Insert raw data AS-IS into Bronze tables (RAW.IOT_READINGS, RAW.OPENAQ_RAW)
3. Clean + transform both sources
4. Combine + insert into Silver table (CLEAN.AQI_CLEAN)
"""

import os
import pandas as pd
import numpy as np
import snowflake.connector
from dotenv import load_dotenv

# ---------------------------------------------------------
# 0. LOAD ENV VARIABLES + SNOWFLAKE CONNECTION
# ---------------------------------------------------------
load_dotenv()

SNOWFLAKE_CONFIG = {
    "account": os.environ.get("SNOWFLAKE_ACCOUNT"),
    "user": os.environ.get("SNOWFLAKE_USER"),
    "password": os.environ.get("SNOWFLAKE_PASSWORD"),
    "warehouse": os.environ.get("SNOWFLAKE_WAREHOUSE"),
    "database": os.environ.get("SNOWFLAKE_DATABASE"),
    "role": os.environ.get("SNOWFLAKE_ROLE"),
}

IOT_CSV = os.path.join("data", "iot_readings.csv")
OPENAQ_CSV = os.path.join("data", "openaq_readings.csv")


def get_connection():
    return snowflake.connector.connect(**SNOWFLAKE_CONFIG)


# ---------------------------------------------------------
# 1. AQI CATEGORY + HEALTH RISK HELPERS (EPA BREAKPOINTS)
# ---------------------------------------------------------
AQI_BREAKPOINTS = [
    (0.0, 12.0, "Good"),
    (12.1, 35.4, "Moderate"),
    (35.5, 55.4, "Unhealthy for Sensitive Groups"),
    (55.5, 150.4, "Unhealthy"),
    (150.5, 250.4, "Very Unhealthy"),
    (250.5, 500.4, "Hazardous"),
]

HEALTH_RISK_MAP = {
    "Good": "LOW",
    "Moderate": "LOW",
    "Unhealthy for Sensitive Groups": "MEDIUM",
    "Unhealthy": "HIGH",
    "Very Unhealthy": "HIGH",
    "Hazardous": "CRITICAL",
}


def aqi_category_from_pm25(pm25):
    if pd.isna(pm25):
        return None
    pm25 = max(0.0, min(pm25, 500.4))
    for lo, hi, label in AQI_BREAKPOINTS:
        if lo <= pm25 <= hi:
            return label
    return "Hazardous"


def health_risk_from_category(category):
    if category is None:
        return None
    return HEALTH_RISK_MAP.get(category, "MEDIUM")


# ---------------------------------------------------------
# 2. LOAD RAW DATA INTO BRONZE (AS-IS, NO CLEANING)
# ---------------------------------------------------------
def load_iot_to_bronze(conn, df_iot: pd.DataFrame):
    cursor = conn.cursor()
    insert_sql = """
        INSERT INTO RAW.IOT_READINGS
        (sensor_id, city, zone_type, pm25, pm10, co2_ppm, temperature_c,
         humidity_pct, wind_speed_kmh, aqi_value, severity, recorded_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    df_iot = df_iot[[
        "sensor_id", "city", "zone_type", "pm25", "pm10", "co2_ppm",
        "temperature_c", "humidity_pct", "wind_speed_kmh", "aqi_value",
        "severity", "recorded_at",
    ]]

    # NaN ko None banao warna Snowflake NAN literal token bhej deta hai
    df_iot = df_iot.astype(object).where(pd.notnull(df_iot), None)
    rows = df_iot.values.tolist()

    cursor.executemany(insert_sql, rows)
    conn.commit()
    cursor.close()
    print(f"  -> Inserted {len(rows)} raw rows into RAW.IOT_READINGS")


def load_openaq_to_bronze(conn, df_openaq: pd.DataFrame):
    cursor = conn.cursor()
    insert_sql = """
        INSERT INTO RAW.OPENAQ_RAW
        (location_id, station_name, city, country_code, latitude, longitude,
         pollutant_type, pollutant_value, unit, recorded_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    df_openaq = df_openaq[[
        "location_id", "station_name", "city", "country_code",
        "latitude", "longitude", "pollutant_type", "pollutant_value",
        "unit", "recorded_at",
    ]]

    # NaN ko None banao warna Snowflake NAN literal token bhej deta hai
    df_openaq = df_openaq.astype(object).where(pd.notnull(df_openaq), None)
    rows = df_openaq.values.tolist()

    cursor.executemany(insert_sql, rows)
    conn.commit()
    cursor.close()
    print(f"  -> Inserted {len(rows)} raw rows into RAW.OPENAQ_RAW")


# ---------------------------------------------------------
# 3. TRANSFORM — IoT DATA (per spec Stage 2 rules)
# ---------------------------------------------------------
def transform_iot(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # Drop rows where pm25 or aqi_value is null
    df = df.dropna(subset=["pm25", "aqi_value"])

    # Validate ranges
    df = df[(df["pm25"] >= 0) & (df["pm25"] <= 500)]
    df = df[(df["co2_ppm"] >= 400) & (df["co2_ppm"] <= 2000)]
    df = df[(df["humidity_pct"] >= 0) & (df["humidity_pct"] <= 100)]

    # Add aqi_category (recomputed from pm25 for consistency)
    df["aqi_category"] = df["pm25"].apply(aqi_category_from_pm25)

    # Add health_risk
    df["health_risk"] = df["aqi_category"].apply(health_risk_from_category)

    # Deduplicate on (sensor_id, recorded_at)
    df = df.drop_duplicates(subset=["sensor_id", "recorded_at"])

    # Add processed_at timestamp (tz-naive UTC, native python datetime)
    df["processed_at"] = pd.Timestamp.now(tz="UTC").tz_localize(None).to_pydatetime()

    # Add fields to match Silver schema
    df["source"] = "iot_simulator"
    df["latitude"] = np.nan
    df["longitude"] = np.nan

    return df[[
        "source", "city", "sensor_id", "pm25", "pm10", "co2_ppm",
        "aqi_value", "aqi_category", "health_risk", "latitude",
        "longitude", "recorded_at", "processed_at",
    ]]


# ---------------------------------------------------------
# 4. TRANSFORM — OpenAQ DATA (per spec Stage 2 rules)
# ---------------------------------------------------------
def transform_openaq(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # Filter to pm25 and pm10 parameters only
    df = df[df["pollutant_type"].isin(["pm25", "pm10"])]

    # Drop rows where pollutant_value <= 0
    df = df[df["pollutant_value"] > 0]

    # Convert recorded_at to UTC then strip tz (column is TIMESTAMP_NTZ in Snowflake)
    df["recorded_at"] = pd.to_datetime(df["recorded_at"], utc=True, errors="coerce").dt.tz_localize(None)
    df = df.dropna(subset=["recorded_at"])

    # Pivot so pm25 and pm10 become columns on the same row
    # (group by station + timestamp so both pollutants line up together)
    pivot = df.pivot_table(
        index=["location_id", "city", "latitude", "longitude", "recorded_at"],
        columns="pollutant_type",
        values="pollutant_value",
        aggfunc="mean",
    ).reset_index()

    # Ensure both columns exist even if one pollutant type was missing entirely
    for col in ["pm25", "pm10"]:
        if col not in pivot.columns:
            pivot[col] = np.nan

    # Add remaining Silver fields
    pivot["co2_ppm"] = np.nan  # OpenAQ doesn't provide CO2
    pivot["aqi_category"] = pivot["pm25"].apply(aqi_category_from_pm25)
    pivot["aqi_value"] = np.nan  # could compute full AQI formula from pm25 if desired
    pivot["health_risk"] = pivot["aqi_category"].apply(health_risk_from_category)
    pivot["source"] = "openaq_v3"
    pivot["sensor_id"] = None
    pivot["processed_at"] = pd.Timestamp.now(tz="UTC").tz_localize(None).to_pydatetime()

    return pivot[[
        "source", "city", "sensor_id", "pm25", "pm10", "co2_ppm",
        "aqi_value", "aqi_category", "health_risk", "latitude",
        "longitude", "recorded_at", "processed_at",
    ]]


# ---------------------------------------------------------
# 5. LOAD CLEANED DATA INTO SILVER
# ---------------------------------------------------------
def load_to_silver(conn, df_clean: pd.DataFrame):
    cursor = conn.cursor()
    insert_sql = """
        INSERT INTO CLEAN.AQI_CLEAN
        (source, city, sensor_id, pm25, pm10, co2_ppm, aqi_value,
         aqi_category, health_risk, latitude, longitude, recorded_at, processed_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """

    # IoT rows have tz-naive recorded_at, OpenAQ rows may mix naive/aware after
    # concat -> always force utc=True first, then strip tz (NTZ columns in Snowflake)
    for col in ["recorded_at", "processed_at"]:
        df_clean[col] = pd.to_datetime(df_clean[col], errors="coerce", utc=True)
        df_clean[col] = df_clean[col].dt.tz_localize(None)

    # Replace NaN with None so Snowflake gets proper NULLs
    df_clean = df_clean.astype(object).where(pd.notnull(df_clean), None)
    rows = df_clean.values.tolist()

    # astype(object) turns datetime values back into pandas.Timestamp objects,
    # which the Snowflake connector cannot bind -> convert to native python datetime
    rows = [
        tuple(v.to_pydatetime() if isinstance(v, pd.Timestamp) else v for v in row)
        for row in rows
    ]

    cursor.executemany(insert_sql, rows)
    conn.commit()
    cursor.close()
    print(f"  -> Inserted {len(rows)} cleaned rows into CLEAN.AQI_CLEAN")


# ---------------------------------------------------------
# 6. MAIN ETL RUN
# ---------------------------------------------------------
def run_etl():
    print("Reading CSV files...")
    df_iot_raw = pd.read_csv(IOT_CSV)
    df_openaq_raw = pd.read_csv(OPENAQ_CSV)
    print(f"  IoT rows: {len(df_iot_raw)} | OpenAQ rows: {len(df_openaq_raw)}\n")

    conn = get_connection()

    print("Step 1: Loading RAW data into Bronze...")
    load_iot_to_bronze(conn, df_iot_raw)
    load_openaq_to_bronze(conn, df_openaq_raw)

    print("\nStep 2: Cleaning + transforming...")
    df_iot_clean = transform_iot(df_iot_raw)
    df_openaq_clean = transform_openaq(df_openaq_raw)
    print(f"  IoT clean rows: {len(df_iot_clean)} | OpenAQ clean rows: {len(df_openaq_clean)}")

    df_combined = pd.concat([df_iot_clean, df_openaq_clean], ignore_index=True)
    print(f"  Combined Silver rows: {len(df_combined)}\n")

    print("Step 3: Loading cleaned data into Silver...")
    load_to_silver(conn, df_combined)

    conn.close()
    print("\nETL pipeline finished successfully.")


if __name__ == "__main__":
    run_etl()
