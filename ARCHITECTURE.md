# Архитектура проекта «Прогноз курса акций»

Документ описывает устройство проекта: стек, структуру, слои, назначение функций,
схему базы данных и потоки данных.

---

## 1. Назначение

Учебный проект по курсу «Базы данных: хранение и передача информации».

Программа:

1. загружает исторические котировки акций (OHLCV) из Yahoo Finance в PostgreSQL;
2. строит прогноз цены на N торговых дней вперёд (ARIMA и наивный бейзлайн);
3. сохраняет прогноз в базу и показывает историю, прогноз и метрики качества
   в веб-интерфейсе.

---

## 2. Языки и технологии

### Языки

| Язык | Где используется |
|---|---|
| **Python 3.10+** | вся логика: ETL, модель, веб-интерфейс |
| **SQL** | DDL (`sql/schema.sql`), DML (`sql/seed_tickers.sql`), запросы в коде |
| **YAML** | `docker-compose.yml` |
| **Make** | `Makefile` (команды запуска) |
| **Dockerfile** | сборка образа приложения |
| **Markdown / Mermaid** | документация и ER-диаграмма |

### Фреймворки и библиотеки

| Компонент | Версия | Роль |
|---|---|---|
| **PostgreSQL** | 14+ (проверено на 16) | СУБД |
| **Streamlit** | ≥ 1.49 | фреймворк веб-интерфейса (серверный рендеринг в браузере) |
| **Plotly** | ≥ 5.18 | интерактивные графики |
| **pandas** | ≥ 2.1 | таблицы, работа с датами, календарь праздников |
| **NumPy** | ≥ 1.26 | численные массивы, метрики |
| **statsmodels** | ≥ 0.14 | модель ARIMA |
| **psycopg2-binary** | ≥ 2.9 | драйвер PostgreSQL (без ORM) |
| **yfinance** | ≥ 0.2.40 | загрузка котировок |
| **python-dateutil** | ≥ 2.8 | дата Страстной пятницы (`easter`) |

ORM не используется: работа идёт через параметризованный SQL — запросы читаемы,
а SQL-инъекции исключены подстановкой параметров.

---

## 3. Структура репозитория

```
stock_prediction-main/
├── app.py                  # Streamlit-интерфейс (слой представления)
├── etl/
│   ├── __init__.py         # пакет ETL
│   ├── db.py               # единая конфигурация подключения к PostgreSQL
│   ├── load_prices.py      # ETL: Yahoo Finance → historical_prices
│   └── predict.py          # доменная логика: обучение, прогноз, бэктест, запись
├── sql/
│   ├── schema.sql          # DDL: таблицы, ограничения, индексы, view
│   └── seed_tickers.sql    # справочник 30 тикеров
├── Dockerfile              # образ приложения
├── docker-compose.yml      # PostgreSQL + приложение
├── Makefile                # install / db / etl / predict / run / check
├── requirements.txt        # прямые зависимости
├── .env.example            # шаблон переменных окружения
├── README.md               # инструкция по запуску
└── ARCHITECTURE.md         # этот документ
```

---

## 4. Архитектура

### 4.1 Слои

Проект разделён на четыре слоя; зависимости идут строго вниз, обратных
зависимостей нет.

| Слой | Файлы | Ответственность |
|---|---|---|
| **Представление** | `app.py` | ввод параметров, график, метрики, таблица |
| **Доменная логика** | `etl/predict.py` | прогноз, бэктест, торговый календарь, запись результата |
| **Загрузка данных (ETL)** | `etl/load_prices.py` | получение OHLCV и идемпотентная запись |
| **Доступ к данным** | `etl/db.py`, SQL внутри модулей | конфигурация и выполнение запросов |
| **Хранилище** | `sql/schema.sql` | таблицы, ограничения, индексы, view |

### 4.2 Поток данных

```mermaid
flowchart LR
    YF[(Yahoo Finance)] -->|yfinance| ETL["etl/load_prices.py"]
    ETL -->|"upsert ON CONFLICT"| HP[(historical_prices)]
    HP -->|"SELECT close"| PRED["etl/predict.py"]
    PRED -->|"ARIMA / naive"| PD[(predictions)]
    PD --> V{{"latest_predictions (view)"}}
    HP --> APP["app.py (Streamlit)"]
    V --> APP
    APP -->|"кнопка «Рассчитать прогноз»"| PRED
```

### 4.3 Принципы

1. **Идемпотентность.** Повторный запуск ETL не создаёт дублей
   (`ON CONFLICT (ticker_id, trade_date)`), повторный прогноз обновляет строку
   (`ON CONFLICT (ticker_id, model_name, target_date)`).
2. **Одна точка конфигурации БД** — `etl/db.py`; остальные модули не знают,
   откуда берутся параметры подключения.
3. **Никакого долгоживущего соединения** в веб-слое: psycopg2 не потокобезопасен,
   а после ошибки транзакция остаётся в состоянии `aborted`. Соединение
   открывается на один запрос и закрывается через `contextlib.closing`.
4. **Валидация на входе домена.** Модель проверяет длину ряда и имя модели
   и бросает `ValueError`; интерфейс показывает текст ошибки, а не traceback.

---

## 5. Модули, классы и функции

> **Про классы.** В проекте нет пользовательских классов: это скрипты и набор
> чистых функций. Причины — малый объём логики, отсутствие состояния между
> вызовами и нативная модель Streamlit (скрипт перезапускается на каждое
> взаимодействие). Состояние, которое всё же нужно сохранять между
> перезапусками, живёт в `st.session_state`, а конфигурация — в словаре
> `DB_CONFIG`. Классы имеет смысл вводить при появлении нескольких моделей
> с общим интерфейсом (см. раздел 9).

### 5.1 `app.py` — слой представления

Модуль исполняется сверху вниз при каждом взаимодействии пользователя
(особенность Streamlit).

| Функция | Назначение |
|---|---|
| `query_df(sql, params=None, columns=None) -> DataFrame` | выполняет один запрос в отдельном соединении и возвращает `DataFrame`; `columns` позволяет задать имена столбцов вручную |
| `load_tickers() -> DataFrame` | справочник тикеров для выпадающего списка; кешируется на 10 минут (`@st.cache_data(ttl=600)`) |
| `get_ticker_id(symbol) -> int` | резолвит тикер в суррогатный ключ `tickers.id` |
| `load_history_df(ticker_id, lookback=730) -> DataFrame` | `trade_date, close` за последние `lookback` дней — для графика |
| `load_recent_predictions(limit=10) -> DataFrame` | последние прогнозы из view с явным `ORDER BY` |

Константы модуля: `LOOKBACK_DAYS`, `PROJECT_YEAR`, `AUTHORS`, `MODEL_LABELS`.

**Поток выполнения скрипта:**

1. сайдбар — выбор тикера, модели, горизонта; кнопка расчёта;
2. чтение истории выбранного тикера; если данных нет — `st.stop()` с подсказкой;
3. по нажатию кнопки: `load_history` → `fit_and_forecast` → `save_predictions` →
   `backtest`; результат кладётся в `st.session_state["forecast"]` вместе
   с параметрами;
4. прогноз показывается только если сохранённые параметры совпадают с текущими
   (иначе пользователь видит устаревший результат для другого горизонта);
5. график Plotly: история + пунктирная линия прогноза;
6. таблица последних прогнозов и подвал с авторами.

### 5.2 `etl/db.py` — конфигурация подключения

| Объект | Назначение |
|---|---|
| `DB_CONFIG: dict` | параметры подключения; собирается из переменных `DB_NAME`, `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`; по умолчанию — локальный unix-сокет |
| `DATABASE_URL: str \| None` | строка подключения целиком; имеет приоритет над `DB_CONFIG` |
| `connect()` | возвращает новое соединение `psycopg2`; закрытие — на вызывающем коде |

### 5.3 `etl/load_prices.py` — ETL

| Функция | Назначение |
|---|---|
| `get_tickers(conn, symbol=None)` | список `(id, symbol)` из `tickers`; при `symbol` — один тикер (регистр не важен) |
| `fetch_prices(symbol, period) -> DataFrame` | загрузка OHLCV через `yfinance`; `auto_adjust=True` — цены скорректированы на сплиты и дивиденды; `MultiIndex` схлопывается до одного уровня |
| `upsert_prices(conn, ticker_id, df) -> int` | пакетная вставка `execute_values` с `ON CONFLICT DO UPDATE`; пропускает строки с `NaN` в `close`; возвращает число строк |
| `_num(v)` / `_int(v)` | приведение `numpy`-типов к `float`/`int` или `None` (для корректной передачи в драйвер) |
| `main()` | CLI: `--period` (по умолчанию `5y`), `--symbol`; ошибка по одному тикеру не прерывает остальные, в конце печатается сводка |

### 5.4 `etl/predict.py` — доменная логика

| Функция | Назначение |
|---|---|
| `load_history(conn, ticker_id, lookback_days=730) -> Series` | `close`, индексированный по `trade_date`; отбрасывает выходные; бросает `ValueError`, если истории нет |
| `_nyse_holidays(start, end) -> set[date]` | праздники NYSE: федеральные праздники США минус День Колумба и День ветеранов, плюс Страстная пятница (`dateutil.easter`) |
| `next_trading_days(last_date, count) -> list[Timestamp]` | следующие `count` торговых дат: только будни и не праздники |
| `fit_and_forecast(series, days, model_name="arima") -> DataFrame` | проверяет `days >= 1` и `len(series) >= MIN_HISTORY`; обучает модель и возвращает `target_date` + `predicted_price` |
| `backtest(series, horizon=14, model_name="arima") -> dict` | обучается без последних `horizon` точек и считает `mae`, `rmse`, `mape`, `naive_mae` |
| `save_predictions(conn, ticker_id, model_name, df) -> int` | upsert в `predictions` с единой меткой времени `prediction_date` на весь пакет |
| `get_ticker(conn, symbol) -> (id, symbol)` | поиск тикера; `ValueError`, если не найден |
| `main()` | CLI: `--symbol`, `--days`, `--model`, `--lookback`, `--no-backtest`; печатает прогноз и метрики |

Константы: `MIN_HISTORY = 30`, `MODELS = ("arima", "naive")`,
`_NYSE_IGNORED_HOLIDAYS`.

**Модели:**

| Имя | Что делает |
|---|---|
| `arima` | `ARIMA(2, 1, 2)` на уровнях цены; индекс сбрасывается на `RangeIndex`, потому что statsmodels не прогнозирует out-of-sample по «рваному» `DatetimeIndex` |
| `naive` | константа «последняя известная цена»; бейзлайн, с которым сравнивается ARIMA |

Обе модели используют один и тот же генератор будущих дат, поэтому результаты
сопоставимы.

---

## 6. База данных

### 6.1 СУБД и модель

**PostgreSQL 14+**, реляционная модель, 3 таблицы и 1 представление.

### 6.2 ER-диаграмма

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
    }
```

### 6.3 Таблицы

#### `tickers` — справочник инструментов

| Поле | Тип | Ограничение | Смысл |
|---|---|---|---|
| `id` | `SERIAL` | PK | суррогатный ключ |
| `symbol` | `VARCHAR(10)` | `NOT NULL UNIQUE` | тикер (`AAPL`) |
| `company_name` | `VARCHAR(255)` | `NOT NULL` | название компании |
| `sector` | `VARCHAR(100)` | — | отрасль |
| `created_at` | `TIMESTAMP` | `NOT NULL DEFAULT NOW()` | когда добавлен |

Родительская таблица: на неё ссылаются обе таблицы фактов. `UNIQUE (symbol)`
делает загрузку справочника идемпотентной (`ON CONFLICT DO NOTHING`).

#### `historical_prices` — временной ряд OHLCV

| Поле | Тип | Ограничение | Смысл |
|---|---|---|---|
| `id` | `BIGSERIAL` | PK | технический ключ |
| `ticker_id` | `INTEGER` | FK → `tickers(id) ON DELETE CASCADE` | инструмент |
| `trade_date` | `DATE` | `NOT NULL` | торговый день |
| `open` / `high` / `low` | `NUMERIC(12,4)` | — | цены открытия, максимум, минимум |
| `close` | `NUMERIC(12,4)` | `NOT NULL` | цена закрытия — источник для модели |
| `volume` | `BIGINT` | — | объём торгов |

Ключевое ограничение: `UNIQUE (ticker_id, trade_date)` — одновременно
бизнес-ключ и гарантия отсутствия дублей при повторной загрузке. Оно же
создаёт B-tree индекс, поэтому отдельный индекс по тем же колонкам не нужен.

#### `predictions` — результаты прогнозов

| Поле | Тип | Ограничение | Смысл |
|---|---|---|---|
| `id` | `BIGSERIAL` | PK | технический ключ |
| `ticker_id` | `INTEGER` | FK → `tickers(id) ON DELETE CASCADE` | инструмент |
| `prediction_date` | `TIMESTAMP` | `NOT NULL DEFAULT NOW()` | когда прогноз посчитан (обновляется при пересчёте) |
| `target_date` | `DATE` | `NOT NULL` | на какой день прогноз |
| `predicted_price` | `NUMERIC(12,4)` | `NOT NULL` | предсказанная цена |
| `model_name` | `VARCHAR(50)` | `NOT NULL` | `arima` / `naive` |

Ограничение `UNIQUE (ticker_id, model_name, target_date)` — основа upsert:
один прогноз на пару «инструмент + модель + дата». Поэтому в таблице хранится
последний расчёт, а не история всех запусков.

### 6.4 Представление `latest_predictions`

```sql
SELECT DISTINCT ON (p.ticker_id, p.model_name)
       t.symbol, t.company_name, p.prediction_date,
       p.target_date, p.predicted_price, p.model_name
FROM predictions p
JOIN tickers t ON t.id = p.ticker_id
ORDER BY p.ticker_id, p.model_name, p.prediction_date DESC, p.target_date ASC;
```

Назначение — «последний прогноз по каждому тикеру и модели»: берётся самый
свежий `prediction_date`, а из него — ближайшая `target_date`. Порядок вывода
задаёт вызывающий запрос: `ORDER BY` внутри view не гарантирован.

### 6.5 Индексы

| Индекс | Зачем |
|---|---|
| `UNIQUE (ticker_id, trade_date)` | идемпотентность ETL + быстрые выборки истории по тикеру и периоду |
| `idx_predictions_ticker_date (ticker_id, target_date)` | выборка прогнозов по инструменту |
| `idx_predictions_prediction_date (prediction_date DESC)` | сортировка «последние прогнозы» в интерфейсе |

### 6.6 Примеры запросов

```sql
-- история за последние полгода
SELECT trade_date, close
FROM historical_prices
WHERE ticker_id = 1 AND trade_date >= CURRENT_DATE - INTERVAL '180 days'
ORDER BY trade_date;

-- последние прогнозы по всем тикерам
SELECT symbol, target_date, predicted_price, model_name
FROM latest_predictions
ORDER BY prediction_date DESC, symbol, target_date;
```

---

## 7. Сценарии работы

### 7.1 Загрузка данных

```
python -m etl.load_prices --period 5y
  └─ get_tickers()            → список тикеров из БД
     └─ для каждого:
        fetch_prices()         → DataFrame из yfinance
        upsert_prices()        → INSERT ... ON CONFLICT DO UPDATE
```

### 7.2 Расчёт прогноза

```
python -m etl.predict --symbol AAPL --days 14 --model arima
  └─ get_ticker()              → ticker_id
     load_history()            → Series close за 2 года
     fit_and_forecast()        → ARIMA → DataFrame(target_date, predicted_price)
     save_predictions()        → upsert в predictions
     backtest()                → MAE / RMSE / MAPE + сравнение с naive
```

### 7.3 Работа в интерфейсе

1. `load_tickers()` (кеш 10 мин) → выпадающий список.
2. `get_ticker_id()` + `load_history_df()` → график истории и текущая цена.
3. Кнопка → тот же путь, что в 7.2, плюс запись в `session_state`.
4. `load_recent_predictions()` → таблица из `latest_predictions`.

---

## 8. Конфигурация

| Источник | Приоритет | Пример |
|---|---|---|
| `DATABASE_URL` | 1 | `postgresql://user:pass@host:5432/stock_prediction` |
| `DB_NAME`, `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD` | 2 | `DB_HOST=localhost` |
| локальный сокет + пользователь ОС | 3 | macOS/Linux по умолчанию |

Шаблон — `.env.example`. Секреты в репозиторий не попадают (`.gitignore`).

---

## 9. Ограничения и направления развития

| Ограничение | Что можно сделать |
|---|---|
| ARIMA на уровнях цены, без сезонности | логарифмические доходности, `SARIMAX` с недельной сезонностью |
| Один отрезок для бэктеста | walk-forward по нескольким окнам, направленная точность |
| `predictions` хранит только последний расчёт | добавить `run_id` и снять уникальность, если нужна история |
| Календарь NYSE зашит в код | `pandas_market_calendars` |
| Нет тестов и CI | `pytest` на `fit_and_forecast` / `next_trading_days` / upsert + GitHub Actions с Postgres-сервисом |
| Функции вместо классов | при росте числа моделей — протокол/базовый класс `Model` с `fit()` / `forecast()` |
