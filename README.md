# Stock Prediction App (Курсовая по БД)

Проект для курса "Базы данных: хранение и передача информации". 
Тема: Предсказание курса акций. 

## Что сделано:
1. **Схема БД (PostgreSQL):** 3 таблицы (`tickers`, `historical_prices`, `predictions`), индексы и VIEW для вывода последних прогнозов. 
2. **Парсер:** качает данные с Yahoo Finance за 5 лет.
3. **Модель:** ARIMA (библиотека `statsmodels`). Читает историю из БД, прогнозирует и сохраняет обратно.
4. **Интерфейс:** Streamlit. Можно выбрать акцию, задать горизонт и увидеть график.

## Как запустить (локально)
1. Создать базу:
   `createdb stock_prediction`
2. Применить схему:
   `psql -d stock_prediction -f sql/schema.sql`
3. Залить тикеры:
   `psql -d stock_prediction -f sql/seed_tickers.sql`
4. Установить зависимости:
   `pip install -r requirements.txt`
5. Запустить ETL:
   `python etl/load_prices.py --period 5y`
6. Запустить UI:
   `streamlit run app/streamlit_app.py`

## Трудности (что было сложно)
* Долго мучился с `ON CONFLICT` при загрузке данных, чтобы не было дублей.
* `yfinance` иногда отдаёт колонки как MultiIndex, пришлось это обрабатывать.
* Статсмоделс падал с ошибкой `No supported index`, пришлось сбрасывать индекс перед ARIMA и генерировать даты вручную.
* В Стримлайте `Decimal` из базы не складывается с `float` от модели, пришлось кастовать.

## ER Diagram
(Сюда нужно будет вставить картинку схемы из draw.io)
