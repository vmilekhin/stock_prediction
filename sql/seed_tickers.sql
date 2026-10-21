-- 10 крупных американских акций для демо
INSERT INTO tickers (symbol, company_name, sector) VALUES
    ('AAPL',  'Apple Inc.',              'Technology'),
    ('MSFT',  'Microsoft Corporation',   'Technology'),
    ('GOOGL', 'Alphabet Inc.',           'Technology'),
    ('AMZN',  'Amazon.com Inc.',         'Consumer Cyclical'),
    ('TSLA',  'Tesla Inc.',              'Consumer Cyclical'),
    ('NVDA',  'NVIDIA Corporation',      'Technology'),
    ('META',  'Meta Platforms Inc.',     'Communication Services'),
    ('NFLX',  'Netflix Inc.',            'Communication Services'),
    ('AMD',   'Advanced Micro Devices',  'Technology'),
    ('INTC',  'Intel Corporation',       'Technology')
ON CONFLICT (symbol) DO NOTHING;
