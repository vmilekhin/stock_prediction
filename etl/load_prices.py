"""
ETL: загрузка исторических котировок из Yahoo Finance в PostgreSQL.
Использование:
    python etl/load_prices.py                # все тикеры, 5 лет
    python etl/load_prices.py --period 2y    # все тикеры, 2 года
    python etl/load_prices.py --symbol AAPL  # только AAPL
"""
import argparse
import sys
from datetime import datetime

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
import yfinance as yf


DB_CONFIG = {"dbname": "stock_prediction"}  # локальный сокет, peer auth


def get_tickers(conn, symbol=None):
    """Возвращает [(id, symbol), ...] из таблицы tickers."""
    with conn.cursor() as cur:
        if symbol:
            cur.execute("SELECT id, symbol FROM tickers WHERE symbol = %s", (symbol,))
        else:
            cur.execute("SELECT id, symbol FROM tickers ORDER BY id")
        return cur.fetchall()


def fetch_prices(symbol: str, period: str) -> pd.DataFrame:
    """Качает OHLCV через yfinance. Возвращает DataFrame с датой в индексе."""
    df = yf.download(symbol, period=period, progress=False, auto_adjust=False)
    if df.empty:
        return df
    # В новых версиях yfinance колонки — MultiIndex (field, ticker).
    # Схлопываем до одного уровня: Open, High, Low, Close, Volume.
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df


def upsert_prices(conn, ticker_id: int, df: pd.DataFrame) -> int:
    """Вставляет/обновляет строки в historical_prices. Возвращает кол-во строк."""
    rows = []
    for trade_date, row in df.iterrows():
        # Пропускаем строки с NaN в close (праздники/сбои)
        close = row.get("Close")
        if pd.isna(close):
            continue
        rows.append((
            ticker_id,
            trade_date.date(),
            _num(row.get("Open")),
            _num(row.get("High")),
            _num(row.get("Low")),
            float(close),
            _int(row.get("Volume")),
        ))
    if not rows:
        return 0
    with conn.cursor() as cur:
        execute_values(
            cur,
            """
            INSERT INTO historical_prices
                (ticker_id, trade_date, open, high, low, close, volume)
            VALUES %s
            ON CONFLICT (ticker_id, trade_date) DO UPDATE SET
                open   = EXCLUDED.open,
                high   = EXCLUDED.high,
                low    = EXCLUDED.low,
                close  = EXCLUDED.close,
                volume = EXCLUDED.volume
            """,
            rows,
        )
    conn.commit()
    return len(rows)


def _num(v):
    return None if pd.isna(v) else float(v)

def _int(v):
    return None if pd.isna(v) else int(v)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--period", default="5y", help="период yfinance, напр. 5y, 2y, 1y")
    parser.add_argument("--symbol", default=None, help="конкретный тикер (иначе все)")
    args = parser.parse_args()

    started = datetime.now()
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        tickers = get_tickers(conn, args.symbol)
        if not tickers:
            print(f"Нет тикеров в БД (symbol={args.symbol})", file=sys.stderr)
            return 1

        total = 0
        for ticker_id, symbol in tickers:
            print(f"[{symbol}] качаю {args.period}...", flush=True)
            df = fetch_prices(symbol, args.period)
            if df.empty:
                print(f"[{symbol}] нет данных — пропускаю", file=sys.stderr)
                continue
            n = upsert_prices(conn, ticker_id, df)
            total += n
            print(f"[{symbol}] +{n} строк (всего {total})", flush=True)

        print(f"\nГотово за {datetime.now() - started}. Вставлено/обновлено: {total}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
