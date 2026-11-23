PYTHON ?= python3
PSQL   ?= psql
DB     ?= stock_prediction

.PHONY: help install db schema seed etl predict run check clean

help:
	@echo "install  - установить зависимости"
	@echo "db       - создать БД и применить схему + справочник тикеров"
	@echo "schema   - применить только схему"
	@echo "seed     - залить справочник тикеров"
	@echo "etl      - скачать котировки за 5 лет"
	@echo "predict  - прогноз AAPL на 14 торговых дней"
	@echo "run      - запустить веб-интерфейс"
	@echo "check    - проверка синтаксиса Python"

install:
	$(PYTHON) -m pip install -r requirements.txt

db:
	createdb $(DB) || true
	$(MAKE) schema

schema:
	$(PSQL) -d $(DB) -v ON_ERROR_STOP=1 -f sql/schema.sql

seed:
	$(PSQL) -d $(DB) -v ON_ERROR_STOP=1 -f sql/seed_tickers.sql

etl:
	$(PYTHON) -m etl.load_prices --period 5y

predict:
	$(PYTHON) -m etl.predict --symbol AAPL --days 14

run:
	$(PYTHON) -m streamlit run app.py

check:
	$(PYTHON) -m py_compile app.py etl/*.py

clean:
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
