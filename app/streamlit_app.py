import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psycopg2
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from etl.predict import DB_CONFIG, get_ticker, load_history, fit_and_forecast, save_predictions

# --- Настройки страницы ---
st.set_page_config(page_title="Stock Prediction", page_icon="🚀", layout="wide", initial_sidebar_state="expanded")

# --- Красивый CSS (сделано с душой) ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@400;600;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Montserrat', sans-serif;
    }
    
    /* Легкий градиентный фон для всего приложения */
    .stApp {
        background: linear-gradient(135deg, #f5f7fa 0%, #e4e8ec 100%);
    }
    
    /* Сайдбар */
    [data-testid="stSidebar"] {
        background-color: #ffffff;
        box-shadow: 2px 0 10px rgba(0,0,0,0.05);
    }
    
    /* Карточки с метриками */
    div[data-testid="stMetric"] {
        background-color: white;
        padding: 15px;
        border-radius: 15px;
        box-shadow: 0 4px 15px rgba(0,0,0,0.05);
        border-left: 5px solid #4A90E2; /* Синяя полоска */
    }
    /* Делаем разные цвета полосок для разных карточек */
    div[data-testid="stMetric"]:nth-child(1) { border-left-color: #4A90E2; } /* Синий */
    div[data-testid="stMetric"]:nth-child(2) { border-left-color: #27AE60; } /* Зеленый */
    div[data-testid="stMetric"]:nth-child(3) { border-left-color: #8E44AD; } /* Фиолетовый */
    
    div[data-testid="stMetricValue"] > div {
        color: #2C3E50;
        font-weight: 700;
    }
    
    /* Кнопка */
    div.stButton > button {
        background: linear-gradient(90deg, #4A90E2 0%, #357ABD 100%);
        color: white;
        border-radius: 10px;
        font-weight: 600;
        border: none;
        padding: 0.6rem 2rem;
        transition: transform 0.2s;
    }
    div.stButton > button:hover {
        transform: scale(1.02);
        color: white;
    }
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
            "SELECT trade_date, close FROM historical_prices "
            "WHERE ticker_id = %s AND trade_date >= (CURRENT_DATE - INTERVAL '%s days') "
            "ORDER BY trade_date", (ticker_id, lookback))
        rows = cur.fetchall()
    return pd.DataFrame(rows, columns=["trade_date", "close"])

def load_recent_predictions(limit: int = 10) -> pd.DataFrame:
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM latest_predictions LIMIT %s", (limit,))
        rows = cur.fetchall()
    return pd.DataFrame(rows, columns=["symbol", "company_name", "prediction_date", "target_date", "predicted_price", "model_name"])


# --- Заголовок ---
st.title("📈 Предсказание курса акций")
st.markdown("<p style='font-size: 1.1rem; color: #555;'>Курсовая работа по базам данных: ETL -> PostgreSQL -> ARIMA -> Streamlit</p>", unsafe_allow_html=True)
st.write("---")

# --- Сайдбар с параметрами ---
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/3135/3135715.png", width=80)
    st.header("Панель управления")
    
    tickers_df = load_tickers()
    symbol = st.selectbox(
        "Выберите акцию:",
        options=tickers_df["symbol"].tolist(),
        format_func=lambda s: f"{s} ({tickers_df.loc[tickers_df.symbol == s, 'company_name'].iloc[0]})",
    )
    
    st.subheader("Настройки прогноза")
    days = st.slider("На сколько дней вперед?", 7, 30, 14)
    lookback = st.selectbox("Глубина истории (дней)", [365, 730, 1095], index=1)
    
    predict_btn = st.button("🔮 Сделать прогноз", use_container_width=True)
    
    st.info("💡 **Как это работает:** Модель ARIMA читает историю цен из базы данных, обучается и сохраняет результат обратно в таблицу `predictions`.")

# --- Получаем данные ---
conn = get_conn()
ticker_id, _ = get_ticker(conn, symbol)
hist_df = load_history_df(ticker_id, lookback)

if hist_df.empty:
    st.error(f"❌ Для тикера {symbol} нет данных в базе. Запустите ETL-скрипт.")
    st.stop()

last_price = float(hist_df['close'].iloc[-1])

# --- Блок с метриками ---
col1, col2, col3 = st.columns(3)
col1.metric("Текущая цена", f"${last_price:.2f}")

forecast_df = None
if predict_btn:
    with st.spinner("Нейросеть думает... (обучение ARIMA)"):
        series = load_history(conn, ticker_id, lookback)
        forecast_df = fit_and_forecast(series, days, "arima")
        save_predictions(conn, ticker_id, "arima", forecast_df)
    
    target_price = float(forecast_df['predicted_price'].iloc[-1])
    delta = target_price - last_price
    
    col2.metric(f"Прогноз через {days} дн.", f"${target_price:.2f}", f"{delta:+.2f} USD")
    col3.metric("Статус", "Сохранено в БД ✅")
    st.success("Прогноз успешно сгенерирован и записан в PostgreSQL!")
else:
    col2.metric("Прогноз", "—", help="Нажмите кнопку слева")
    col3.metric("Статус", "Ожидание")

# --- График ---
fig = go.Figure()

# История (с заливкой снизу, как в Robinhood)
fig.add_trace(go.Scatter(
    x=hist_df["trade_date"], y=hist_df["close"],
    mode="lines", name="История",
    line=dict(color="#4A90E2", width=3),
    fill='tozeroy', fillcolor='rgba(74, 144, 226, 0.1)', # Голубая заливка
    hovertemplate="Дата: %{x}<br>Цена: $%{y:.2f}<extra></extra>"
))

if predict_btn and forecast_df is not None:
    # Прогноз (яркая линия)
    fig.add_trace(go.Scatter(
        x=forecast_df["target_date"], y=forecast_df["predicted_price"],
        mode="lines+markers", name="Прогноз",
        line=dict(color="#27AE60", width=3, dash="dot"),
        marker=dict(size=8, color="#27AE60"),
        hovertemplate="Дата: %{x}<br>Прогноз: $%{y:.2f}<extra></extra>"
    ))
    # Соединяющая линия
    fig.add_trace(go.Scatter(
        x=[hist_df["trade_date"].iloc[-1], forecast_df["target_date"].iloc[0]],
        y=[last_price, float(forecast_df["predicted_price"].iloc[0])],
        mode="lines", line=dict(color="#27AE60", width=2, dash="dot"),
        showlegend=False, hoverinfo="skip"
    ))

fig.update_layout(
    height=500,
    title=f"Динамика акций {symbol}",
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    xaxis=dict(showgrid=True, gridcolor="#e0e0e0"),
    yaxis=dict(showgrid=True, gridcolor="#e0e0e0", title="Цена, USD", tickprefix="$"),
    hovermode="x unified",
    margin=dict(l=40, r=40, t=60, b=40),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
)
st.plotly_chart(fig, use_container_width=True)

# --- Таблица последних прогнозов ---
st.write("---")
st.subheader("📋 Последние записи в базе (VIEW latest_predictions)")
st.caption("Таблица показывает, что результаты работы модели физически сохраняются в БД.")

recent = load_recent_predictions(10)
if not recent.empty:
    st.dataframe(
        recent, 
        use_container_width=True, 
        hide_index=True,
        column_config={
            "predicted_price": st.column_config.NumberColumn("Цена", format="$%.2f"),
            "target_date": st.column_config.DateColumn("На дату", format="DD.MM.YYYY"),
            "prediction_date": st.column_config.DatetimeColumn("Время прогноза", format="DD.MM.YYYY HH:mm"),
        }
    )
else:
    st.write("Пока нет сохраненных прогнозов. Нажмите кнопку 'Сделать прогноз'.")
