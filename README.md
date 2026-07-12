# Smart City Air Quality Monitoring System

**Data Engineering Hackathon Project**
Instructor: Ayan Hussain

An end-to-end data pipeline that simulates IoT air-quality sensors across five
Pakistani cities (Karachi, Lahore, Islamabad, Peshawar, Multan), fetches real
reference data from the OpenAQ V3 API, cleans and combines both sources through
a Python ETL pipeline, stores the results in Snowflake using a Bronze / Silver /
Gold (medallion) architecture, and visualizes everything in a live, auto-refreshing
Streamlit dashboard.

## Problem Statement

Pakistan's major cities face serious air pollution challenges, and municipal
governments have deployed IoT sensors across industrial zones, traffic hotspots,
residential areas, and parks. However, sensor data alone doesn't provide a complete
picture. This project compares simulated IoT sensor readings against real monitoring
station data from OpenAQ, enabling analysis of pollution patterns, underreported
areas, and when public health alerts should be issued.

## Architecture

```
 IoT Simulator (Python)                OpenAQ V3 API
        │                                     │
        ▼                                     ▼
 RAW.IOT_READINGS                     RAW.OPENAQ_RAW          <- Bronze (raw, as-is)
        │                                     │
        └──────────────┬──────────────────────┘
                        ▼
                CLEAN.AQI_CLEAN                                <- Silver (validated, combined)
                        │
                        ▼
              ANALYTICS.CITY_DAILY                             <- Gold (daily aggregates)
                        │
                        ▼
              Streamlit Dashboard
```

- **Bronze** — raw data loaded as-is from both sources, no cleaning applied
- **Silver** — validated, range-checked, deduplicated, and combined into one table
  with a consistent schema across both sources
- **Gold** — daily per-city aggregates (avg/max/min AQI, dominant health risk,
  reading counts) used to power dashboard KPIs

## Tech Stack

| Layer            | Tool                                   |
|-------------------|-----------------------------------------|
| Sensor simulation  | Python (`random`, `time`, `datetime`)   |
| Reference data     | OpenAQ V3 API (`requests`)              |
| ETL                | Pandas                                  |
| Data warehouse     | Snowflake (Bronze / Silver / Gold)      |
| Dashboard          | Streamlit                               |

## Project Structure

```
Smart_City_AQI/
├── simulator/
│   └── iot_simulator.py        # generates simulated sensor readings every 10s
├── openaq/
│   └── openaq_fetcher.py       # pulls Pakistan station data from OpenAQ V3
├── etl/
│   └── etl_pipeline.py         # cleans + loads both sources into Snowflake
├── sql/
│   ├── schema.sql              # Bronze / Silver / Gold table definitions
│   └── gold_load.sql           # aggregates Silver -> Gold
├── dashboard/
│   └── app.py                  # Streamlit dashboard
├── data/
│   ├── iot_readings.csv
│   └── openaq_readings.csv
├── screenshots/
│   ├── 01_simulator.png
│   ├── 02_openaq_fetcher.png
│   ├── 03_etl_pipeline.png
│   ├── 04_bronze_tables.png
│   ├── 05_silver_gold_tables.png
│   └── 06_dashboard.png
├── .env                         # credentials (not committed to git)
├── .gitignore
├── requirements.txt
└── README.md
```

> Adjust the `simulator/` and `openaq/` file names above if your actual scripts
> are named differently.

## Prerequisites

- Python 3.10+
- A free [Snowflake trial account](https://signup.snowflake.com/)
- A free [OpenAQ API key](https://explore.openaq.org/register)

## Setup

### 1. Clone the repo and create a virtual environment

```bash
git clone <your-repo-url>
cd Smart_City_AQI
python -m venv venv
venv\Scripts\activate        # Windows
pip install -r requirements.txt
```

### 2. Configure environment variables

Create a `.env` file in the project root:

```
SNOWFLAKE_ACCOUNT=your_account
SNOWFLAKE_USER=your_user
SNOWFLAKE_PASSWORD=your_password
SNOWFLAKE_WAREHOUSE=your_warehouse
SNOWFLAKE_DATABASE=SMART_CITY_AQI
SNOWFLAKE_ROLE=your_role
OPENAQ_API_KEY=your_openaq_key
```

### 3. Create the Snowflake schema

Open a Snowflake worksheet (Snowsight) and run the contents of `sql/schema.sql`.
This creates the `SMART_CITY_AQI` database with `RAW`, `CLEAN`, and `ANALYTICS`
schemas, along with all four tables (`IOT_READINGS`, `OPENAQ_RAW`, `AQI_CLEAN`,
`CITY_DAILY`).

## Running the Pipeline

Run each stage in order:

```bash
# 1. Generate simulated IoT sensor readings (let it run 30+ minutes for enough data)
python simulator/iot_simulator.py

# 2. Fetch real reference data from OpenAQ V3 for Pakistan locations
python openaq/openaq_fetcher.py

# 3. Clean, transform, and load both sources into Snowflake (Bronze -> Silver)
python etl/etl_pipeline.py
```

Then, in a Snowflake worksheet, populate the Gold layer by running the contents
of `sql/gold_load.sql`. Re-run this after every new ETL load to refresh the daily
aggregates.

## Running the Dashboard

```bash
streamlit run dashboard/app.py
```

Opens at `http://localhost:8501`. Data refreshes automatically every 30 seconds
(`st.cache_data(ttl=30)`). The dashboard includes:

- **Bar chart** — average AQI per city, today
- **Line chart** — AQI trend per sensor, last 6 hours
- **KPI cards** — highest AQI city, total readings, % CRITICAL readings
- **Severity badges** — 🟢 LOW / 🟡 MEDIUM / 🔴 HIGH / 🟣 CRITICAL per reading
- **Gold layer table** — daily city-level aggregates

## Data Notes

- OpenAQ monitoring stations in Pakistan are concentrated in Karachi and Lahore;
  where a city has no station, the nearest available location is used for
  comparison rather than an exact city match.
- IoT sensor readings include a 15% chance of an anomaly spike (2.5–4x PM2.5
  multiplier) to simulate real pollution events, and a time-of-day multiplier
  that peaks around 8 AM and 6 PM.
- AQI values are computed using the EPA breakpoint formula from PM2.5 readings.

## Deliverables Checklist

- [x] IoT simulator script
- [x] OpenAQ fetcher script
- [x] ETL pipeline script
- [x] Snowflake SQL (`sql/schema.sql`, `sql/gold_load.sql`)
- [x] Dashboard (`dashboard/app.py`)
- [ ] Screenshots of all 6 deliverables (see below)
- [ ] 5-minute live demo

## Screenshots

![Simulator running](screenshots/01_simulator.png)
![OpenAQ fetcher](screenshots/02_openaq_fetcher.png)
![ETL pipeline](screenshots/03_etl_pipeline.png)
![Bronze tables](screenshots/04_bronze_tables.png)
![Silver and Gold tables](screenshots/05_silver_gold_tables.png)
![Live dashboard](screenshots/06_dashboard.png)

## Demo Flow (5 minutes)

1. Start the simulator live — show console printing UNHEALTHY/HAZARDOUS readings
2. Query `RAW.IOT_READINGS` in Snowsight — show data arriving in real time
3. Run the ETL pipeline — show Bronze → Silver load messages
4. Run the Gold layer SQL — show `ANALYTICS.CITY_DAILY` populated
5. Open the dashboard — walk through the charts, KPI cards, and severity badges
