"""
Smart City AQI - Streamlit Dashboard
Reads from Snowflake Gold (ANALYTICS.CITY_DAILY) and Silver (CLEAN.AQI_CLEAN) layers.
Run with: streamlit run dashboard/app.py

Theme: white/light (see .streamlit/config.toml alongside this file).
Charts: kept simple - a pie chart for city share and one for severity mix,
plus a plain line chart for the AQI trend. No dense multi-series clutter.
"""

import os
import pandas as pd
import streamlit as st
import plotly.express as px
import snowflake.connector
from dotenv import load_dotenv

load_dotenv()

SNOWFLAKE_CONFIG = {
    "account": os.environ.get("SNOWFLAKE_ACCOUNT"),
    "user": os.environ.get("SNOWFLAKE_USER"),
    "password": os.environ.get("SNOWFLAKE_PASSWORD"),
    "warehouse": os.environ.get("SNOWFLAKE_WAREHOUSE"),
    "database": os.environ.get("SNOWFLAKE_DATABASE"),
    "role": os.environ.get("SNOWFLAKE_ROLE"),
}

st.set_page_config(page_title="Smart City AQI Dashboard", layout="wide")

# ---------------------------------------------------------
# Simple, consistent color mapping used across every chart
# ---------------------------------------------------------
SEVERITY_COLORS = {
    "LOW": "#22C55E",       # green
    "MEDIUM": "#EAB308",    # yellow
    "HIGH": "#F97316",      # orange
    "CRITICAL": "#DC2626",  # red
}
SEVERITY_BADGE = {
    "LOW": "🟢 LOW",
    "MEDIUM": "🟡 MEDIUM",
    "HIGH": "🟠 HIGH",
    "CRITICAL": "🔴 CRITICAL",
}

# Plotly layout defaults so every chart matches the white theme
PLOTLY_LAYOUT = dict(
    paper_bgcolor="#FFFFFF",
    plot_bgcolor="#FFFFFF",
    font=dict(color="#111111"),
    margin=dict(l=10, r=10, t=40, b=10),
)


# ---------------------------------------------------------
# CONNECTION (cached across reruns, not re-opened every 30s)
# ---------------------------------------------------------
@st.cache_resource
def get_connection():
    return snowflake.connector.connect(**SNOWFLAKE_CONFIG)


def run_query(query: str) -> pd.DataFrame:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(query)
    return cur.fetch_pandas_all()


# ---------------------------------------------------------
# DATA LOADERS (cached 30s -> auto-refresh)
# ---------------------------------------------------------
@st.cache_data(ttl=30)
def load_city_daily():
    return run_query("SELECT * FROM ANALYTICS.CITY_DAILY ORDER BY REPORT_DATE DESC")


@st.cache_data(ttl=30)
def load_today_city_avg():
    return run_query("""
        SELECT CITY, AVG(AQI_VALUE) AS AVG_AQI
        FROM CLEAN.AQI_CLEAN
        WHERE CAST(RECORDED_AT AS DATE) = CURRENT_DATE()
          AND AQI_VALUE IS NOT NULL
        GROUP BY CITY
        ORDER BY AVG_AQI DESC
    """)


@st.cache_data(ttl=30)
def load_sensor_trend():
    return run_query("""
        SELECT SENSOR_ID, RECORDED_AT, AQI_VALUE
        FROM CLEAN.AQI_CLEAN
        WHERE SENSOR_ID IS NOT NULL
          AND RECORDED_AT >= DATEADD(hour, -6, CURRENT_TIMESTAMP())
        ORDER BY RECORDED_AT
    """)


@st.cache_data(ttl=30)
def load_recent_readings():
    return run_query("""
        SELECT SOURCE, CITY, SENSOR_ID, PM25, AQI_VALUE, HEALTH_RISK, RECORDED_AT
        FROM CLEAN.AQI_CLEAN
        ORDER BY RECORDED_AT DESC
        LIMIT 50
    """)


@st.cache_data(ttl=30)
def load_severity_mix():
    return run_query("""
        SELECT HEALTH_RISK, COUNT(*) AS READING_COUNT
        FROM CLEAN.AQI_CLEAN
        WHERE HEALTH_RISK IS NOT NULL
        GROUP BY HEALTH_RISK
    """)


@st.cache_data(ttl=30)
def load_city_share():
    return run_query("""
        SELECT CITY, COUNT(*) AS READING_COUNT
        FROM CLEAN.AQI_CLEAN
        WHERE CITY IS NOT NULL
        GROUP BY CITY
        ORDER BY READING_COUNT DESC
    """)


@st.cache_data(ttl=30)
def load_kpis():
    df = run_query("""
        SELECT
            COUNT(*) AS TOTAL_READINGS,
            SUM(CASE WHEN HEALTH_RISK = 'CRITICAL' THEN 1 ELSE 0 END) AS CRITICAL_COUNT
        FROM CLEAN.AQI_CLEAN
    """)
    return df.iloc[0]


# ---------------------------------------------------------
# HEADER
# ---------------------------------------------------------
st.title("Smart City Air Quality Dashboard — Pakistan")
st.caption("Live data from IoT sensors + OpenAQ V3 · auto-refreshes every 30 seconds")

# ---------------------------------------------------------
# KPI METRIC CARDS
# ---------------------------------------------------------
city_avg = load_today_city_avg()
kpis = load_kpis()

col1, col2, col3 = st.columns(3)

if not city_avg.empty:
    top = city_avg.iloc[0]
    col1.metric("Highest AQI City (today)", top["CITY"], f"{top['AVG_AQI']:.1f} AQI")
else:
    col1.metric("Highest AQI City (today)", "No data yet")

col2.metric("Total Readings", int(kpis["TOTAL_READINGS"]))

total = int(kpis["TOTAL_READINGS"])
critical = int(kpis["CRITICAL_COUNT"]) if kpis["CRITICAL_COUNT"] is not None else 0
critical_pct = (critical / total * 100) if total > 0 else 0
col3.metric("% CRITICAL Readings", f"{critical_pct:.1f}%")

st.divider()

# ---------------------------------------------------------
# PIE CHARTS — city share + severity mix, side by side
# ---------------------------------------------------------
pie_col1, pie_col2 = st.columns(2)

with pie_col1:
    st.subheader("Readings by City")
    city_share = load_city_share()
    if not city_share.empty:
        fig = px.pie(city_share, names="CITY", values="READING_COUNT", hole=0.45)
        fig.update_traces(textinfo="label+percent")
        fig.update_layout(**PLOTLY_LAYOUT, showlegend=False)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No readings yet.")

with pie_col2:
    st.subheader("Severity Mix")
    severity_mix = load_severity_mix()
    if not severity_mix.empty:
        fig = px.pie(
            severity_mix, names="HEALTH_RISK", values="READING_COUNT", hole=0.45,
            color="HEALTH_RISK", color_discrete_map=SEVERITY_COLORS,
        )
        fig.update_traces(textinfo="label+percent")
        fig.update_layout(**PLOTLY_LAYOUT, showlegend=False)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No readings yet.")

st.divider()

# ---------------------------------------------------------
# BAR CHART — avg AQI per city today (magnitude comparison,
# kept as a plain bar since AQI isn't a proportion / doesn't
# suit a pie chart)
# ---------------------------------------------------------
st.subheader("Average AQI per City — Today")
if not city_avg.empty:
    fig = px.bar(city_avg, x="CITY", y="AVG_AQI", color_discrete_sequence=["#2563EB"])
    fig.update_layout(**PLOTLY_LAYOUT)
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("No readings recorded for today yet.")

# ---------------------------------------------------------
# LINE CHART — AQI trend per sensor, last 6 hours
# ---------------------------------------------------------
st.subheader("AQI Trend per Sensor — Last 6 Hours")
trend = load_sensor_trend()
if not trend.empty:
    fig = px.line(trend, x="RECORDED_AT", y="AQI_VALUE", color="SENSOR_ID")
    fig.update_layout(**PLOTLY_LAYOUT)
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("No sensor readings in the last 6 hours yet. Run the IoT simulator to generate live data.")

# ---------------------------------------------------------
# SEVERITY TABLE
# ---------------------------------------------------------
st.subheader("Recent Readings — Severity Badges")
recent = load_recent_readings()
if not recent.empty:
    recent = recent.copy()
    recent["SEVERITY"] = recent["HEALTH_RISK"].map(SEVERITY_BADGE).fillna("⚪ UNKNOWN")
    st.dataframe(
        recent[["SOURCE", "CITY", "SENSOR_ID", "PM25", "AQI_VALUE", "SEVERITY", "RECORDED_AT"]],
        use_container_width=True,
        hide_index=True,
    )
else:
    st.info("No readings found in CLEAN.AQI_CLEAN yet.")

# ---------------------------------------------------------
# GOLD LAYER TABLE
# ---------------------------------------------------------
st.subheader("Daily City Aggregates (Gold Layer)")
daily = load_city_daily()
if not daily.empty:
    st.dataframe(daily, use_container_width=True, hide_index=True)
else:
    st.info("ANALYTICS.CITY_DAILY is empty — run the Gold layer INSERT SQL first.")