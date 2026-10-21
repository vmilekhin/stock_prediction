# Предсказание курса акций (Задание по БД)

## 🗄️ Реализация базы данных (PostgreSQL)
Спроектирована схема из 3 таблиц со связями (внешние ключи) и индексами:
* `tickers` — справочник акций.
* `historical_prices` — исторические котировки (OHLCV).
* `predictions` — результаты предсказаний модели.
Также создано `VIEW latest_predictions` для быстрого вывода последних прогнозов.

## 📊 ER-диаграмма
```mermaid
erDiagram
    TICKERS ||--o{ HISTORICAL_PRICES : "has"
    TICKERS ||--o{ PREDICTIONS : "has"

    TICKERS {
        int id PK
        varchar symbol
        varchar company_name
        varchar sector
        timestamp created_at
    }

    HISTORICAL_PRICES {
        bigint id PK
        int ticker_id FK
        date trade_date
        numeric open
        numeric high
        numeric low
        numeric close
        bigint volume
    }

    PREDICTIONS {
        bigint id PK
        int ticker_id FK
        timestamp prediction_date
        date target_date
        numeric predicted_price
        varchar model_name
        timestamp created_at
    }
