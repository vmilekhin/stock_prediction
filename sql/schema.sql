-- ============================================================
-- Stock Prediction — схема БД
-- Курс: Базы данных: хранение и передача информации
-- Скрипт идемпотентен: можно применять повторно на существующей БД.
-- ============================================================

-- Справочник тикеров (акций)
CREATE TABLE IF NOT EXISTS tickers (
    id            SERIAL PRIMARY KEY,
    symbol        VARCHAR(10)  NOT NULL UNIQUE,
    company_name  VARCHAR(255) NOT NULL,
    sector        VARCHAR(100),
    created_at    TIMESTAMP    NOT NULL DEFAULT NOW()
);

-- Исторические котировки (OHLCV)
CREATE TABLE IF NOT EXISTS historical_prices (
    id          BIGSERIAL PRIMARY KEY,
    ticker_id   INTEGER       NOT NULL REFERENCES tickers(id) ON DELETE CASCADE,
    trade_date  DATE          NOT NULL,
    open        NUMERIC(12,4),
    high        NUMERIC(12,4),
    low         NUMERIC(12,4),
    close       NUMERIC(12,4) NOT NULL,
    volume      BIGINT,
    UNIQUE (ticker_id, trade_date)
);

-- UNIQUE (ticker_id, trade_date) уже создаёт B-tree индекс ровно по этим
-- колонкам, поэтому отдельный индекс был избыточен (лишняя запись при вставке).
DROP INDEX IF EXISTS idx_historical_prices_ticker_date;

-- Прогнозы, сделанные моделью
-- prediction_date — когда прогноз был посчитан (обновляется при пересчёте)
CREATE TABLE IF NOT EXISTS predictions (
    id              BIGSERIAL PRIMARY KEY,
    ticker_id       INTEGER       NOT NULL REFERENCES tickers(id) ON DELETE CASCADE,
    prediction_date TIMESTAMP     NOT NULL DEFAULT NOW(),
    target_date     DATE          NOT NULL,
    predicted_price NUMERIC(12,4) NOT NULL,
    model_name      VARCHAR(50)   NOT NULL
);

-- created_at дублировал prediction_date (оба DEFAULT NOW()) — убираем
ALTER TABLE predictions DROP COLUMN IF EXISTS created_at;

-- Чистим дубли, накопившиеся до появления уникального ключа
DELETE FROM predictions p
USING predictions q
WHERE p.id < q.id
  AND p.ticker_id = q.ticker_id
  AND p.model_name = q.model_name
  AND p.target_date = q.target_date;

-- Один прогноз на (тикер, модель, дата) — повторный запуск делает upsert,
-- а не добавляет новые строки
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'predictions_ticker_model_target_uniq'
    ) THEN
        ALTER TABLE predictions
            ADD CONSTRAINT predictions_ticker_model_target_uniq
            UNIQUE (ticker_id, model_name, target_date);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_predictions_ticker_date
    ON predictions (ticker_id, target_date);

-- Для сортировки «последние прогнозы» в интерфейсе
CREATE INDEX IF NOT EXISTS idx_predictions_prediction_date
    ON predictions (prediction_date DESC);

-- Последний посчитанный прогноз по каждому тикеру и модели
-- (ближайшая дата из последнего запуска).
-- ORDER BY нужен только для DISTINCT ON; порядок вывода задаёт вызывающий запрос.
CREATE OR REPLACE VIEW latest_predictions AS
SELECT DISTINCT ON (p.ticker_id, p.model_name)
    t.symbol,
    t.company_name,
    p.prediction_date,
    p.target_date,
    p.predicted_price,
    p.model_name
FROM predictions p
JOIN tickers t ON t.id = p.ticker_id
ORDER BY p.ticker_id, p.model_name, p.prediction_date DESC, p.target_date ASC;
