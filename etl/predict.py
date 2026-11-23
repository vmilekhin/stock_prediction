"""
Прогноз цены акции на N торговых дней вперёд.

Логика:
  1. Читаем close из historical_prices для тикера.
  2. Обучаем модель на последних ~2 годах истории.
  3. Генерируем прогноз на N торговых дней вперёд.
  4. Пишем результат в predictions (upsert по ticker_id + model_name + target_date).

Модели:
  arima — ARIMA(2, 1, 2) на уровнях цены (statsmodels)
  naive — наивный прогноз «последняя известная цена» (бейзлайн для сравнения)

Использование:
    python -m etl.predict --symbol AAPL --days 14
    python etl/predict.py --symbol AAPL --days 30 --model naive
"""
import argparse
import sys
import warnings
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from dateutil.easter import easter
from pandas.tseries.holiday import USFederalHolidayCalendar
from psycopg2.extras import execute_values
from statsmodels.tsa.arima.model import ARIMA

if __package__ in (None, ""):  # запуск как `python etl/predict.py`
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from etl.db import DB_CONFIG, connect  # noqa: E402

# Меньше этого числа наблюдений ARIMA(2,1,2) обучать бессмысленно
MIN_HISTORY = 30
MODELS = ("arima", "naive")

# Праздники, которые NYSE не отмечает, хотя они федеральные
_NYSE_IGNORED_HOLIDAYS = {"Columbus Day", "Veterans Day"}


def load_history(conn, ticker_id: int, lookback_days: int = 730) -> pd.Series:
    """Возвращает Series close, индексированный по trade_date, только торговые дни."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT trade_date, close
            FROM historical_prices
            WHERE ticker_id = %s
              AND trade_date >= CURRENT_DATE - make_interval(days => %s)
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
    # В базе уже только торговые дни, но на всякий случай отбрасываем выходные
    s = s[s.index.dayofweek < 5]
    if s.empty:
        raise ValueError(f"Нет торговых дней в истории для ticker_id={ticker_id}")
    return s


def _nyse_holidays(start: date, end: date) -> set:
    """Праздники NYSE в диапазоне [start, end]."""
    holidays = set()
    calendar = USFederalHolidayCalendar()
    for rule in calendar.rules:
        if rule.name in _NYSE_IGNORED_HOLIDAYS:
            continue
        for day in rule.dates(start, end):
            holidays.add(day.date())
    # Страстная пятница — не федеральный праздник, но биржа закрыта
    for year in range(start.year, end.year + 1):
        good_friday = easter(year) - timedelta(days=2)
        if start <= good_friday <= end:
            holidays.add(good_friday)
    return holidays


def next_trading_days(last_date: pd.Timestamp, count: int) -> list:
    """Следующие `count` торговых дат после last_date (без выходных и праздников NYSE)."""
    start = last_date.date() + timedelta(days=1)
    horizon_end = start + timedelta(days=count * 2 + 45)
    holidays = _nyse_holidays(start, horizon_end)

    days = []
    cur = start
    while len(days) < count:
        if cur.weekday() < 5 and cur not in holidays:
            days.append(pd.Timestamp(cur))
        cur += timedelta(days=1)
    return days


def fit_and_forecast(series: pd.Series, days: int, model_name: str = "arima") -> pd.DataFrame:
    """Возвращает DataFrame [target_date, predicted_price] на `days` торговых дней."""
    if days < 1:
        raise ValueError("Горизонт прогноза должен быть >= 1 торгового дня")
    if len(series) < MIN_HISTORY:
        raise ValueError(
            f"Слишком мало истории: {len(series)} торговых дней, нужно минимум {MIN_HISTORY}"
        )

    model_name = model_name.lower()
    if model_name not in MODELS:
        raise ValueError(f"Неизвестная модель {model_name!r}, доступны: {', '.join(MODELS)}")

    last_date = series.index[-1]

    if model_name == "naive":
        predicted = np.full(days, float(series.iloc[-1]), dtype=float)
    else:
        # statsmodels не умеет out-of-sample прогноз с «рваным» DatetimeIndex
        # (выходные и праздники выброшены), поэтому сбрасываем индекс на RangeIndex,
        # а реальные даты генерируем отдельно.
        values = series.reset_index(drop=True).astype(float)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            fitted = ARIMA(values, order=(2, 1, 2)).fit()
        predicted = np.asarray(fitted.forecast(steps=days), dtype=float)

    return pd.DataFrame({
        "target_date": next_trading_days(last_date, days),
        "predicted_price": predicted,
    })


def backtest(series: pd.Series, horizon: int = 14, model_name: str = "arima") -> dict:
    """Оценка качества: обучаемся без последних `horizon` дней и сравниваем с фактом."""
    if len(series) < MIN_HISTORY + horizon:
        raise ValueError(
            f"Для бэктеста нужно минимум {MIN_HISTORY + horizon} торговых дней, "
            f"есть {len(series)}"
        )

    train = series.iloc[:-horizon]
    actual = series.iloc[-horizon:].to_numpy(dtype=float)
    predicted = fit_and_forecast(train, horizon, model_name)["predicted_price"].to_numpy()
    naive = np.full(horizon, float(train.iloc[-1]))

    def mae(p, a):
        return float(np.mean(np.abs(p - a)))

    def rmse(p, a):
        return float(np.sqrt(np.mean((p - a) ** 2)))

    def mape(p, a):
        mask = a != 0
        return float(np.mean(np.abs((a[mask] - p[mask]) / a[mask])) * 100)

    return {
        "mae": mae(predicted, actual),
        "rmse": rmse(predicted, actual),
        "mape": mape(predicted, actual),
        "naive_mae": mae(naive, actual),
    }


def save_predictions(conn, ticker_id: int, model_name: str, df: pd.DataFrame) -> int:
    """Пишет прогнозы в predictions (upsert). Возвращает число строк."""
    predicted_at = datetime.now()
    rows = [
        (ticker_id, model_name, r.target_date.date(), float(r.predicted_price), predicted_at)
        for r in df.itertuples(index=False)
    ]
    with conn.cursor() as cur:
        execute_values(
            cur,
            """
            INSERT INTO predictions
                (ticker_id, model_name, target_date, predicted_price, prediction_date)
            VALUES %s
            ON CONFLICT (ticker_id, model_name, target_date) DO UPDATE SET
                predicted_price = EXCLUDED.predicted_price,
                prediction_date = EXCLUDED.prediction_date
            """,
            rows,
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
    parser.add_argument("--model", default="arima", choices=MODELS, help="модель прогноза")
    parser.add_argument("--lookback", type=int, default=730, help="сколько дней истории брать (по умолчанию 2 года)")
    parser.add_argument("--no-backtest", action="store_true", help="не считать метрики качества")
    args = parser.parse_args()

    conn = connect()
    try:
        ticker_id, symbol = get_ticker(conn, args.symbol)
        print(f"[{symbol}] читаю историю (lookback={args.lookback} дн.)...")
        series = load_history(conn, ticker_id, args.lookback)
        print(f"[{symbol}] {len(series)} торговых дней: {series.index[0].date()} .. {series.index[-1].date()}")

        print(f"[{symbol}] обучаю {args.model.upper()} и прогнозирую на {args.days} торг. дн....")
        df = fit_and_forecast(series, args.days, args.model)

        n = save_predictions(conn, ticker_id, args.model, df)
        print(f"[{symbol}] сохранено {n} прогнозов в predictions")

        if not args.no_backtest:
            try:
                m = backtest(series, horizon=args.days, model_name=args.model)
                print(
                    f"[{symbol}] бэктест {args.days} дн.: MAE={m['mae']:.2f} USD, "
                    f"RMSE={m['rmse']:.2f}, MAPE={m['mape']:.2f}% "
                    f"(наивный MAE={m['naive_mae']:.2f})"
                )
            except ValueError as exc:
                print(f"[{symbol}] бэктест пропущен: {exc}")

        print("\nПервые 5 строк прогноза:")
        print(df.head().to_string(index=False))
        return 0
    except ValueError as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
