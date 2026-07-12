# 🌍 Smart City Air Quality Monitoring System

**Data Engineering Hackathon Project**

An end-to-end data engineering pipeline that simulates IoT air quality sensors across five Pakistani cities, combines them with real OpenAQ data, processes everything using a Medallion Architecture (Bronze, Silver, Gold), stores the data in Snowflake, and visualizes insights using Streamlit.

---

## 🚀 Features

- IoT air quality sensor simulation
- OpenAQ V3 API integration
- Python ETL with Pandas
- Snowflake Bronze → Silver → Gold pipeline
- Interactive Streamlit dashboard
- Daily AQI analytics and KPIs

---

## 🏗️ Architecture

```text
IoT Simulator        OpenAQ API
      │                  │
      └──────┬───────────┘
             ▼
      Bronze (RAW)
             ▼
      Silver (CLEAN)
             ▼
      Gold (ANALYTICS)
             ▼
    Streamlit Dashboard
```

---

## 🛠️ Tech Stack

- Python
- Pandas
- OpenAQ API
- Snowflake
- Streamlit

---

## 📁 Project Structure

```text
Smart_City_AQI/
│
├── simulator/
├── openaq/
├── etl/
├── sql/
├── dashboard/
├── data/
├── screenshots/
├── .env
├── requirements.txt
└── README.md
```

---

## ⚙️ Setup

### Clone Repository

```bash
git clone <repo-url>
cd Smart_City_AQI
```

### Install Dependencies

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### Configure Environment

Create a `.env` file:

```env
SNOWFLAKE_ACCOUNT=
SNOWFLAKE_USER=
SNOWFLAKE_PASSWORD=
SNOWFLAKE_DATABASE=SMART_CITY_AQI
SNOWFLAKE_WAREHOUSE=
SNOWFLAKE_ROLE=
OPENAQ_API_KEY=
```

---

## ▶️ Run Project

### 1. Generate IoT Data

```bash
python simulator/iot_simulator.py
```

### 2. Fetch OpenAQ Data

```bash
python openaq/openaq_fetcher.py
```

### 3. Run ETL

```bash
python etl/etl_pipeline.py
```

### 4. Load Gold Layer

Execute:

```text
sql/gold_load.sql
```

### 5. Launch Dashboard

```bash
streamlit run dashboard/app.py
```

---

## 📊 Dashboard

- AQI by City
- AQI Trends
- KPI Cards
- Severity Levels
- Daily Gold Layer Summary

---

## 📸 Screenshots

```
screenshots/
├── 01_simulator.png
├── 02_openaq_fetcher.png
├── 03_etl_pipeline.png
├── 04_bronze_tables.png
├── 05_silver_gold_tables.png
└── 06_dashboard.png
```

---

## 📦 Project Workflow

```text
Simulate Data
      ↓
Fetch OpenAQ Data
      ↓
ETL Processing
      ↓
Load into Snowflake
      ↓
Create Gold Layer
      ↓
Visualize in Streamlit
```

---

## 👨‍💻 Author

**Muhammad Mohsin**

Data Engineering Hackathon Project
