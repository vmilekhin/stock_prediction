"""
Streamlit UI для Stock Prediction.
Запуск: streamlit run app/streamlit_app.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psycopg2
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from etl.predict import DB_CONFIG, get_ticker, load_history, fit_and_forecast, save_predictions

# --- Настройки страницы ---
st.set_page_config(page_title="Stock Insight", page_icon="📈", layout="wide", initial_sidebar_state="expanded")

# --- Кастомный CSS (делаем UI человеческим) ---
st.markdown("""
<style>
    /* Импорт шрифта Inter */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
        color: #1E293B;
    }
    
    /* Фон приложения */
    .stApp {
        background-color: #F8FAFC;
    }
    
    /* Стилизация сайдбара */
    [data-testid="stSidebar"] {
        background-color: #FFFFFF;
        border-right: 1px solid #E2E8F0;
    }
    
    /* Стилизация карточек метрик */
    div[data-testid="stMetric"] {
        background-color: #FFFFFF;
        padding: 20px;
        border-radius: 12px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.03);
        border: 1px solid #E2E8F0;
    }
    div[data-testid="stMetricLabel"] > div {
        font-weight: 500;
        color: #64748B !important;
        font-size: 0.9rem;
    }
    div[data-testid="stMetricValue"] > div {
        color: #0F172A;
        font-weight: 700;
    }
    
    /* Кнопка Predict */
    div.stButton > button {
        background-color: #2563EB;
        color: white;
        border-radius: 8px;
        font-weight: 600;
        border: none;
        padding: 0.6rem 1rem;
        transition: all 0.2s ease;
    }
    div.stButton > button:hover {
        background-color: #1D4ED8;
        box-shadow: 0 4px 12px rgba(37, 99, 235, 0.3);
    }
    
    /* Убираем дефолтный футер Streamlit */
    footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)


@st.cache_resource
def get_conn():
    return psycopg2.connect(**DB_CONFIG)

def load_tickers() -> pd.DataFrame:
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("SELECT symbol, company_name FROM tickers ORDER BY symbol")
        rows = cur.fetchall()
    return pd.DataFrame(rows, columns=["symbol", "company_name"])

def load_history_df(ticker_id: int, lookback: int) -> pd.DataFrame:
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT trade_date, open, high, low, close, volume FROM historical_prices "
            "WHERE ticker_id = %s AND trade_date >= (CURRENT_DATE - INTERVAL '%s days') "
            "ORDER BY trade_date", (ticker_id, lookback))
        rows = cur.fetchall()
    return pd.DataFrame(rows, columns=["trade_date", "open", "high", "low", "close", "volume"])

def load_recent_predictions(limit: int = 20) -> pd.DataFrame:
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM latest_predictions LIMIT %s", (limit,))
        rows = cur.fetchall()
    return pd.DataFrame(rows, columns=["symbol", "company_name", "prediction_date", "target_date", "predicted_price", "model_name"])

# --- UI Layout ---
st.title("📈 Stock Insight")
st.markdown("<p style='color: #64748B; font-size: 1.1rem; margin-top: -10px;'>Аналитика и прогнозирование на базе PostgreSQL + ARIMA</p>", unsafe_allow_html=True)
st.divider()

tickers_df = load_tickers()
if tickers_df.empty:
    st.error("В таблице tickers нет данных. Запусти sql/seed_tickers.sql.")
    st.stop()

with st.sidebar:
    st.markdown("### Параметры")
    symbol = st.selectbox(
        "Тикер",
        options=tickers_df["symbol"].tolist(),
        format_func=lambda s: f"{s} — {tickers_df.loc[tickers_df.symbol == s, 'company_name'].iloc[0]}",
    )
    days = st.slider("Горизонт (торговых дней)", 7, 30, 14)
    lookback = st.selectbox("История для обучения (дней)", [365, 730, 1095, 1825], index=1,
                            format_func=lambda d: f"{d} дн. (~{d // 365} г.)")
    predict_btn = st.button("Сгенерировать прогноз", type="primary", width="stretch")
    st.divider()
    st.caption("Данные: Yahoo Finance\nМодель: ARIMA(2,1,2)\nБД: PostgreSQL")

conn = get_conn()
ticker_id, _ = get_ticker(conn, symbol)
hist_df = load_history_df(ticker_id, lookback)
last_price = float(hist_df['close'].iloc[-1])

# Заголовок выбранной акции
st.subheader(f"{symbol} — {tickers_df.loc[tickers_df.symbol == symbol, 'company_name'].iloc[0]}")

# Блок метрик (отображается всегда)
col1, col2, col3 = st.columns(3)
col1.metric("Последняя цена", f"${last_price:.2f}")

forecast_df = None
if predict_btn:
    with st.spinner("Обучение модели и запись в БД..."):
        series = load_history(conn, ticker_id, lookback)
        forecast_df = fit_and_forecast(series, days, "arima")
        save_predictions(conn, ticker_id, "arima", forecast_df)
        st.success(f"Прогноз на {days} дней успешно сохранен в базу данных!")
    
    target_price = float(forecast_df['predicted_price'].iloc[-1])
    delta = target_price - last_price
    col2.metric(f"Прогноз (через {days} дн.)", f"${target_price:.2f}", f"{delta:+.2f} USD", delta_color="normal")
    col3.metric("Модель", "ARIMA (2,1,2)")
else:
    col2.metric("Прогноз", "—", help="Нажмите 'Сгенерировать прогноз'")
    col3.metric("Модель", "ARIMA (2,1,2)")

# График
fig = go.Figure()

# История
fig.add_trace(go.Scatter(
    x=hist_df["trade_date"], y=hist_df["close"],
    mode="lines", name="История",
    line=dict(color="#3B82F6", width=2),
    hovertemplate="Дата: %{x}<br>Цена: $%{y:.2f}<extra></extra>"
))

if predict_btn and forecast_df is not None:
    # Прогноз
    fig.add_trace(go.Scatter(
        x=forecast_df["target_date"], y=forecast_df["predicted_price"],
        mode="lines+markers", name="Прогноз ARIMA",
        line=dict(color="#10B981", width=2, dash="dot"),
        marker=dict(size=6),
        hovertemplate="Дата: %{x}<br>Прогноз: $%{y:.2f}<extra></extra>"
    ))
    # Линия соединения
    fig.add_trace(go.Scatter(
        x=[hist_df["trade_date"].iloc[-1], forecast_df["target_date"].iloc[0]],
        y=[last_price, float(forecast_df["predicted_price"].iloc[0])],
        mode="lines", line=dict(color="#10B981", width=1, dash="dot"),
        showlegend=False, hoverinfo="skip"
    ))

fig.update_layout(
    height=500,
    margin=dict(l=20, r=20, t=20, b=20),
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    xaxis=dict(showgrid=True, gridcolor="#E2E8F0", title=""),
    yaxis=dict(showgrid=True, gridcolor="#E2E8F0", title="Цена, USD", tickprefix="$"),
    hovermode="x unified",
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
)
st.plotly_chart(fig, width="stretch")

# Таблица последних прогнозов
st.divider()
st.subheader("Последние прогнозы в базе")
recent = load_recent_predictions(10)
st.dataframe(
    recent, 
    width="stretch", 
    hide_index=True,
    column_config={
        "predicted_price": st.column_config.NumberColumn("Цена", format="$%.2f"),
        "prediction_date": st.column_config.DatetimeColumn("Дата прогноза", format="D MMM YYYY, HH:mm"),
        "target_date": st.column_config.DateColumn("На дату", format="D MMM YYYY"),
    }
)
