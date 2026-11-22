"""
ETL: загрузка исторических котировок из Yahoo Finance в PostgreSQL.

Использование:
    python -m etl.load_prices                # все тикеры, 5 лет
    python -m etl.load_prices --period 2y    # все тикеры, 2 года
    python -m etl.load_prices --symbol AAPL  # только AAPL
"""
import argparse
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
from psycopg2.extras import execute_values

if __package__ in (None, ""):  # запуск как `python etl/load_prices.py`
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from etl.db import connect  # noqa: E402


def get_tickers(conn, symbol=None):
    """Возвращает [(id, symbol), ...] из таблицы tickers."""
    with conn.cursor() as cur:
        if symbol:
            cur.execute("SELECT id, symbol FROM tickers WHERE symbol = %s", (symbol.upper(),))
        else:
            cur.execute("SELECT id, symbol FROM tickers ORDER BY id")
        return cur.fetchall()


def fetch_prices(symbol: str, period: str) -> pd.DataFrame:
    """Качает OHLCV через yfinance. Возвращает DataFrame с датой в индексе."""
    try:
        import yfinance as yf
    except ImportError as exc:  # понятная ошибка вместо ImportError из недр
        raise RuntimeError("Не установлен yfinance: pip install yfinance") from exc

    # auto_adjust=True: цены скорректированы на сплиты и дивиденды,
    # иначе в истории появляются фиктивные «обвалы» на сплитах.
    df = yf.download(symbol, period=period, progress=False, auto_adjust=True)
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
    conn = connect()
    try:
        tickers = get_tickers(conn, args.symbol)
        if not tickers:
            if args.symbol:
                print(f"Тикер {args.symbol.upper()} не найден в таблице tickers", file=sys.stderr)
            else:
                print("Таблица tickers пуста — примените sql/seed_tickers.sql", file=sys.stderr)
            return 1

        total, failed = 0, []
        for ticker_id, symbol in tickers:
            print(f"[{symbol}] качаю {args.period}...", flush=True)
            try:
                df = fetch_prices(symbol, args.period)
                if df.empty:
                    print(f"[{symbol}] Yahoo Finance не вернул данных — пропускаю", file=sys.stderr)
                    failed.append(symbol)
                    continue
                n = upsert_prices(conn, ticker_id, df)
            except Exception as exc:  # один битый тикер не должен ронять весь ETL
                conn.rollback()
                print(f"[{symbol}] ошибка: {exc}", file=sys.stderr)
                failed.append(symbol)
                continue

            total += n
            print(f"[{symbol}] +{n} строк (всего {total})", flush=True)

        print(f"\nГотово за {datetime.now() - started}. Вставлено/обновлено: {total}")
        if failed:
            print(f"Не удалось загрузить: {', '.join(failed)}", file=sys.stderr)
            return 1
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
