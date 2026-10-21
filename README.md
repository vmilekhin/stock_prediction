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

## ⚙️ Что делает программа
1. **ETL-скрипт (`etl/load_prices.py`)**: скачивает историю с Yahoo Finance за 5 лет и загружает в базу. Используется `ON CONFLICT`, чтобы при повторном запуске не было дублей.
2. **Модуль предсказания (`etl/predict.py`)**: берет данные из таблицы `historical_prices`, обучает модель `ARIMA` из `statsmodels` и сохраняет прогноз обратно в таблицу `predictions`.
3. **Веб-интерфейс (`app.py`)**: написан на Streamlit. Позволяет выбрать тикер из базы, задать горизонт прогноза и посмотреть график.

## 🚀 Как запустить
1. Создать базу данных:
   `createdb stock_prediction`
2. Применить схему:
   `psql -d stock_prediction -f sql/schema.sql`
   `psql -d stock_prediction -f sql/seed_tickers.sql`
3. Установить зависимости:
   `pip install -r requirements.txt`
4. Запустить загрузку данных (займет ~15 сек):
   `python etl/load_prices.py --period 5y`
5. Запустить интерфейс:
   `streamlit run app.py`

## 🛠️ Трудности при разработке
* В начале данные дублировались при повторной загрузке, решил через `ON CONFLICT (ticker_id, trade_date)`.
* `statsmodels` выдавал ошибку `No supported index` из-за пропусков (выходных) в датах. Пришлось сбрасывать индекс перед обучением.
* В интерфейсе при вычитании цен из БД (тип `Decimal`) и прогноза (тип `float`) вылетал `TypeError`. Исправил явным приведением типов.

## ⚙️ Что делает программа
1. **ETL-скрипт (`etl/load_prices.py`)**: скачивает историю с Yahoo Finance за 5 лет и загружает в базу. Используется `ON CONFLICT`, чтобы при повторном запуске не было дублей.
2. **Модуль предсказания (`etl/predict.py`)**: берет данные из таблицы `historical_prices`, обучает модель `ARIMA` из `statsmodels` и сохраняет прогноз обратно в таблицу `predictions`.
3. **Веб-интерфейс (`app.py`)**: написан на Streamlit. Позволяет выбрать тикер из базы, задать горизонт прогноза и посмотреть график.

## 🚀 Как запустить
1. Создать базу данных:
   `createdb stock_prediction`
2. Применить схему:
   `psql -d stock_prediction -f sql/schema.sql`
   `psql -d stock_prediction -f sql/seed_tickers.sql`
3. Установить зависимости:
   `pip install -r requirements.txt`
4. Запустить загрузку данных (займет ~15 сек):
   `python etl/load_prices.py --period 5y`
5. Запустить интерфейс:
   `streamlit run app.py`

## 🛠️ Трудности при разработке
* В начале данные дублировались при повторной загрузке, решил через `ON CONFLICT (ticker_id, trade_date)`.
* `statsmodels` выдавал ошибку `No supported index` из-за пропусков (выходных) в датах. Пришлось сбрасывать индекс перед обучением.
* В интерфейсе при вычитании цен из БД (тип `Decimal`) и прогноза (тип `float`) вылетал `TypeError`. Исправил явным приведением типов.
