"""
Прогноз цены акции на N торговых дней вперёд.

Логика:
  1. Читаем close из historical_prices для тикера.
  2. Обучаем ARIMA (statsmodels) на последних ~2 годах (или всей истории).
  3. Генерируем прогноз на N дней вперёд.
  4. Пишем результат в predictions (ticker_id, target_date, predicted_price, model_name).

Использование:
    python etl/predict.py --symbol AAPL --days 14
    python etl/predict.py --symbol AAPL --days 30 --model sarimax
"""
import argparse
import sys
import warnings
from datetime import timedelta

import numpy as np
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
from statsmodels.tsa.arima.model import ARIMA


DB_CONFIG = {"dbname": "stock_prediction"}


def load_history(conn, ticker_id: int, lookback_days: int = 730) -> pd.Series:
    """Возвращает Series close, индексированный по trade_date, только торговые дни."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT trade_date, close
            FROM historical_prices
            WHERE ticker_id = %s
              AND trade_date >= (CURRENT_DATE - INTERVAL '%s days')
            ORDER BY trade_date
            """,
            (ticker_id, lookback_days),
        )
        rows = cur.fetchall()
    if not rows:
        raise ValueError(f"Нет истории для ticker_id={ticker_id}")
    s = pd.Series(
        [float(r[1]) for r in rows],
        index=pd.to_datetime([r[0] for r in rows]),
        name="close",
    )
    # Убираем выходные/праздники — оставляем только будни, чтобы ARIMA не спотыкалась
    s = s[s.index.dayofweek < 5]
    return s


def fit_and_forecast(series: pd.Series, days: int, model_name: str) -> pd.DataFrame:
    """Обучает ARIMA(p,d,q) и возвращает DataFrame [target_date, predicted_price]."""
    # statsmodels не умеет out-of-sample прогноз с «рваным» DatetimeIndex
    # (у нас выброшены выходные/праздники). Сохраняем последнюю дату и
    # сбрасываем индекс на RangeIndex — прогноз будет по шагам, а реальные
    # даты сгенерируем вручную ниже.
    last_date = series.index[-1]
    series = series.reset_index(drop=True)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model = ARIMA(series, order=(2, 1, 2))
        fitted = model.fit()

    # Прогноз на `days` торговых дней вперёд
    forecast = fitted.forecast(steps=days)

    # Генерируем будущие торговые даты (пропускаем выходные)
    future_dates = []
    cur = last_date
    while len(future_dates) < days:
        cur = cur + timedelta(days=1)
        if cur.dayofweek < 5:  # пн–пт
            future_dates.append(cur)

    return pd.DataFrame({
        "target_date": future_dates,
        "predicted_price": np.asarray(forecast, dtype=float),
    })


def save_predictions(conn, ticker_id: int, model_name: str, df: pd.DataFrame) -> int:
    """Пишет прогнозы в predictions. Возвращает число строк."""
    rows = [
        (ticker_id, model_name, r.target_date.date(), float(r.predicted_price))
        for r in df.itertuples(index=False)
    ]
    with conn.cursor() as cur:
        execute_values(
            cur,
            """
            INSERT INTO predictions
                (ticker_id, model_name, target_date, predicted_price)
            VALUES %s
            """,
            rows,
            template="(%s, %s, %s, %s)",
        )
    conn.commit()
    return len(rows)


def get_ticker(conn, symbol: str):
    with conn.cursor() as cur:
        cur.execute("SELECT id, symbol FROM tickers WHERE symbol = %s", (symbol,))
        row = cur.fetchone()
    if not row:
        raise ValueError(f"Тикер {symbol} не найден в tickers")
    return row  # (id, symbol)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", required=True, help="например, AAPL")
    parser.add_argument("--days", type=int, default=14, help="горизонт прогноза (торговых дней)")
    parser.add_argument("--model", default="arima", help="имя модели (сохранится в БД)")
    parser.add_argument("--lookback", type=int, default=730, help="сколько дней истории брать (по умолчанию 2 года)")
    args = parser.parse_args()

    conn = psycopg2.connect(**DB_CONFIG)
    try:
        ticker_id, symbol = get_ticker(conn, args.symbol)
        print(f"[{symbol}] читаю историю (lookback={args.lookback} дн.)...")
        series = load_history(conn, ticker_id, args.lookback)
        print(f"[{symbol}] {len(series)} торговых дней: {series.index[0].date()} .. {series.index[-1].date()}")

        print(f"[{symbol}] обучаю {args.model.upper()} и прогнозирую на {args.days} дн....")
        df = fit_and_forecast(series, args.days, args.model)

        n = save_predictions(conn, ticker_id, args.model, df)
        print(f"[{symbol}] сохранено {n} прогнозов в predictions")
        print("\nПервые 5 строк прогноза:")
        print(df.head().to_string(index=False))
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
