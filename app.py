import sys
from contextlib import closing
from pathlib import Path

# Корень проекта — чтобы `from etl... import` работал при `streamlit run app.py`
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd
import plotly.graph_objects as go
import psycopg2
import streamlit as st

from etl.db import DB_CONFIG
from etl.predict import backtest, fit_and_forecast, get_ticker, load_history, save_predictions

LOOKBACK_DAYS = 730
PROJECT_YEAR = 2026  # год создания проекта
AUTHORS = "Милехин Виктор · Пономарев Александр"
MODEL_LABELS = {
    "arima": "ARIMA(2,1,2)",
    "naive": "Наивный (последняя цена)",
}

st.set_page_config(page_title="Прогноз акций", layout="wide")


def query_df(sql: str, params=None, columns=None) -> pd.DataFrame:
    """Один запрос — одно соединение: psycopg2 не потокобезопасен,
    а долгоживущее соединение после ошибки залипает в состоянии aborted."""
    with closing(psycopg2.connect(**DB_CONFIG)) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            rows = cur.fetchall()
            names = columns or [d[0] for d in cur.description]
    return pd.DataFrame(rows, columns=names)


@st.cache_data(ttl=600)
def load_tickers() -> pd.DataFrame:
    return query_df("SELECT symbol, company_name FROM tickers ORDER BY symbol")


def get_ticker_id(symbol: str) -> int:
    with closing(psycopg2.connect(**DB_CONFIG)) as conn:
        return get_ticker(conn, symbol)[0]


def load_history_df(ticker_id: int, lookback: int = LOOKBACK_DAYS) -> pd.DataFrame:
    return query_df(
        "SELECT trade_date, close FROM historical_prices "
        "WHERE ticker_id = %s AND trade_date >= CURRENT_DATE - make_interval(days => %s) "
        "ORDER BY trade_date",
        (ticker_id, lookback),
    )


def load_recent_predictions(limit: int = 10) -> pd.DataFrame:
    # Явные колонки + ORDER BY: порядок строк из view не гарантирован
    return query_df(
        "SELECT symbol, company_name, prediction_date, target_date, predicted_price, model_name "
        "FROM latest_predictions "
        "ORDER BY prediction_date DESC, symbol, target_date "
        "LIMIT %s",
        (limit,),
    )


st.title("Прогноз курса акций")

with st.sidebar:
    st.header("Параметры")

    tickers_df = load_tickers()
    if tickers_df.empty:
        st.error("Таблица tickers пуста — примените sql/seed_tickers.sql")
        st.stop()

    names = dict(zip(tickers_df["symbol"], tickers_df["company_name"]))

    symbol = st.selectbox(
        "Выберите тикер",
        options=tickers_df["symbol"].tolist(),
        format_func=lambda s: f"{s} ({names[s]})",
    )
    model = st.selectbox(
        "Модель",
        options=list(MODEL_LABELS),
        format_func=lambda m: MODEL_LABELS[m],
    )
    days = st.slider("Горизонт (торговых дней)", 7, 30, 14)
    predict_btn = st.button("Рассчитать прогноз", width="stretch")

ticker_id = get_ticker_id(symbol)
hist_df = load_history_df(ticker_id)

if hist_df.empty:
    st.error("Нет данных для этого тикера. Запустите ETL: python -m etl.load_prices")
    st.stop()

last_price = float(hist_df["close"].iloc[-1])
current_params = (symbol, days, model)

# Прогноз храним в session_state: иначе он исчезает при любом rerun Streamlit
st.session_state.setdefault("forecast", None)

if predict_btn:
    try:
        with st.spinner(f"Обучение модели {MODEL_LABELS[model]}..."):
            with closing(psycopg2.connect(**DB_CONFIG)) as conn:
                series = load_history(conn, ticker_id, LOOKBACK_DAYS)
                forecast_df = fit_and_forecast(series, days, model)
                save_predictions(conn, ticker_id, model, forecast_df)

            try:
                metrics = backtest(series, horizon=days, model_name=model)
            except ValueError:
                metrics = None

        st.session_state["forecast"] = {
            "params": current_params,
            "df": forecast_df,
            "metrics": metrics,
        }
        st.success("Прогноз сохранён в базу данных.")
    except ValueError as exc:
        st.session_state["forecast"] = None
        st.error(str(exc))
    except psycopg2.Error as exc:
        st.session_state["forecast"] = None
        st.error(f"Ошибка базы данных: {exc}")

forecast = st.session_state["forecast"]
if forecast and forecast["params"] != current_params:
    forecast = None  # параметры изменились — старый прогноз к ним не относится

# Метрики
col1, col2 = st.columns(2)
col1.metric("Текущая цена", f"${last_price:.2f}")

if forecast:
    target_price = float(forecast["df"]["predicted_price"].iloc[-1])
    delta = target_price - last_price
    col2.metric(f"Прогноз через {days} торг. дн.", f"${target_price:.2f}", f"{delta:+.2f} USD")
else:
    col2.metric("Прогноз", "Нажмите кнопку")

if forecast and forecast["metrics"]:
    m = forecast["metrics"]
    st.caption(
        f"Бэктест на последних {days} торг. днях: "
        f"MAE = {m['mae']:.2f} USD · RMSE = {m['rmse']:.2f} · MAPE = {m['mape']:.2f}% "
        f"(наивный прогноз MAE = {m['naive_mae']:.2f} USD)"
    )

# График
fig = go.Figure()
fig.add_trace(go.Scatter(
    x=hist_df["trade_date"],
    y=hist_df["close"].astype(float),  # из БД приходит Decimal
    mode="lines",
    name="История",
    line=dict(color="blue"),
))

if forecast:
    fig.add_trace(go.Scatter(
        x=forecast["df"]["target_date"],
        y=forecast["df"]["predicted_price"],
        mode="lines+markers",
        name="Прогноз",
        line=dict(color="red", dash="dash"),
    ))

fig.update_layout(
    height=450,
    xaxis_title="Дата",
    yaxis_title="Цена, USD",
    hovermode="x unified",
    margin=dict(l=20, r=20, t=20, b=20),
)
st.plotly_chart(fig, width="stretch")

# Таблица
st.subheader("Последние прогнозы из базы")
recent = load_recent_predictions(10)
st.dataframe(
    recent,
    width="stretch",
    hide_index=True,
    column_config={
        "symbol": st.column_config.TextColumn("Тикер"),
        "company_name": st.column_config.TextColumn("Компания"),
        "prediction_date": st.column_config.DatetimeColumn("Посчитан", format="DD.MM.YYYY HH:mm"),
        "target_date": st.column_config.DateColumn("На дату", format="DD.MM.YYYY"),
        "predicted_price": st.column_config.NumberColumn("Прогноз", format="$%.2f"),
        "model_name": st.column_config.TextColumn("Модель"),
    },
)

# Подвал: авторы и год создания
st.divider()
st.markdown(
    "<div style='text-align:center; color:#8a8a8a; font-size:0.85rem; padding:8px 0 16px;'>"
    f"© {PROJECT_YEAR} · {AUTHORS}"
    "</div>",
    unsafe_allow_html=True,
)
