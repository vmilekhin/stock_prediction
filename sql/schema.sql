-- ============================================================
-- Stock Prediction — схема БД
-- Курс: Базы данных: хранение и передача информации
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

-- Индекс для быстрых выборок «история по тикеру за период»
CREATE INDEX IF NOT EXISTS idx_historical_prices_ticker_date
    ON historical_prices (ticker_id, trade_date);

-- Прогнозы, сделанные моделью
CREATE TABLE IF NOT EXISTS predictions (
    id              BIGSERIAL PRIMARY KEY,
    ticker_id       INTEGER       NOT NULL REFERENCES tickers(id) ON DELETE CASCADE,
    prediction_date TIMESTAMP     NOT NULL DEFAULT NOW(),  -- когда сделан прогноз
    target_date     DATE          NOT NULL,                -- на какой день прогноз
    predicted_price NUMERIC(12,4) NOT NULL,
    model_name      VARCHAR(50)   NOT NULL,                -- 'prophet', 'arima', ...
    created_at      TIMESTAMP     NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_predictions_ticker_date
    ON predictions (ticker_id, target_date);

-- Удобное представление: последние прогнозы по каждому тикеру
CREATE OR REPLACE VIEW latest_predictions AS
SELECT
    t.symbol,
    t.company_name,
    p.prediction_date,
    p.target_date,
    p.predicted_price,
    p.model_name
FROM predictions p
JOIN tickers t ON t.id = p.ticker_id
ORDER BY p.prediction_date DESC, p.target_date ASC;
