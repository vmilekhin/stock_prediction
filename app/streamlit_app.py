import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psycopg2
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from etl.predict import DB_CONFIG, get_ticker, load_history, fit_and_forecast, save_predictions

# Стандартная настройка страницы
st.set_page_config(page_title="Прогноз акций", layout="wide")

@st.cache_resource
def get_conn():
    return psycopg2.connect(**DB_CONFIG)

def load_tickers():
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("SELECT symbol, company_name FROM tickers ORDER BY symbol")
        return pd.DataFrame(cur.fetchall(), columns=["symbol", "company_name"])

def load_history_df(ticker_id: int, lookback: int):
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT trade_date, close FROM historical_prices "
            "WHERE ticker_id = %s AND trade_date >= (CURRENT_DATE - INTERVAL '%s days') "
            "ORDER BY trade_date", (ticker_id, lookback))
        return pd.DataFrame(cur.fetchall(), columns=["trade_date", "close"])

def load_recent_predictions(limit=10):
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM latest_predictions LIMIT %s", (limit,))
        return pd.DataFrame(cur.fetchall(), columns=["symbol", "company_name", "prediction_date", "target_date", "predicted_price", "model_name"])

# Заголовок (без лишнего текста)
st.title("Прогноз курса акций")

# Сайдбар
with st.sidebar:
    st.header("Параметры")
    
    tickers_df = load_tickers()
    symbol = st.selectbox(
        "Выберите тикер",
        options=tickers_df["symbol"].tolist(),
        format_func=lambda s: f"{s} ({tickers_df.loc[tickers_df.symbol == s, 'company_name'].iloc[0]})",
    )
    
    days = st.slider("Горизонт прогноза (дней)", 7, 30, 14)
    predict_btn = st.button("Рассчитать прогноз", use_container_width=True)

# Основной блок
conn = get_conn()
ticker_id, _ = get_ticker(conn, symbol)
hist_df = load_history_df(ticker_id, 730)

if hist_df.empty:
    st.error("Нет данных для этого тикера. Запустите ETL-скрипт.")
    st.stop()

last_price = float(hist_df['close'].iloc[-1])

# Метрики (стандартные, без цветных полосок)
col1, col2 = st.columns(2)
col1.metric("Текущая цена", f"${last_price:.2f}")

forecast_df = None
if predict_btn:
    with st.spinner("Обучение модели..."):
        series = load_history(conn, ticker_id, 730)
        forecast_df = fit_and_forecast(series, days, "arima")
        save_predictions(conn, ticker_id, "arima", forecast_df)
    
    target_price = float(forecast_df['predicted_price'].iloc[-1])
    delta = target_price - last_price
    col2.metric(f"Прогноз через {days} дн.", f"${target_price:.2f}", f"{delta:+.2f} USD")
    st.success("Прогноз сохранен в базу данных.")
else:
    col2.metric("Прогноз", "Нажмите кнопку")

# График (обычные линии, без заливки)
fig = go.Figure()

fig.add_trace(go.Scatter(
    x=hist_df["trade_date"], y=hist_df["close"],
    mode="lines", name="История", line=dict(color="blue")
))

if predict_btn and forecast_df is not None:
    fig.add_trace(go.Scatter(
        x=forecast_df["target_date"], y=forecast_df["predicted_price"],
        mode="lines+markers", name="Прогноз", line=dict(color="red", dash="dash")
    ))

fig.update_layout(
    height=450,
    xaxis_title="Дата",
    yaxis_title="Цена, USD",
    hovermode="x unified",
    margin=dict(l=20, r=20, t=20, b=20)
)
st.plotly_chart(fig, use_container_width=True)

# Таблица
st.subheader("Последние прогнозы из базы")
recent = load_recent_predictions(10)
st.dataframe(recent, use_container_width=True)
