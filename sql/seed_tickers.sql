-- Расширенный список из 30 крупных американских акций
INSERT INTO tickers (symbol, company_name, sector) VALUES
    -- Technology (10)
    ('AAPL',  'Apple Inc.',              'Technology'),
    ('MSFT',  'Microsoft Corporation',   'Technology'),
    ('GOOGL', 'Alphabet Inc.',           'Technology'),
    ('NVDA',  'NVIDIA Corporation',      'Technology'),
    ('AMD',   'Advanced Micro Devices',  'Technology'),
    ('INTC',  'Intel Corporation',       'Technology'),
    ('CSCO',  'Cisco Systems',           'Technology'),
    ('ADBE',  'Adobe Inc.',              'Technology'),
    ('CRM',   'Salesforce Inc.',         'Technology'),
    ('QCOM',  'Qualcomm Inc.',           'Technology'),
    
    -- Consumer Cyclical (5)
    ('AMZN',  'Amazon.com Inc.',         'Consumer Cyclical'),
    ('TSLA',  'Tesla Inc.',              'Consumer Cyclical'),
    ('HD',    'Home Depot Inc.',         'Consumer Cyclical'),
    ('MCD',   'McDonald''s Corporation', 'Consumer Cyclical'),
    ('NKE',   'Nike Inc.',               'Consumer Cyclical'),
    
    -- Communication Services (4)
    ('META',  'Meta Platforms Inc.',     'Communication Services'),
    ('NFLX',  'Netflix Inc.',            'Communication Services'),
    ('DIS',   'Walt Disney Co.',         'Communication Services'),
    ('T',     'AT&T Inc.',               'Communication Services'),
    
    -- Financials (4)
    ('JPM',   'JPMorgan Chase & Co.',    'Financials'),
    ('V',     'Visa Inc.',               'Financials'),
    ('BAC',   'Bank of America Corp.',   'Financials'),
    ('MA',    'Mastercard Inc.',         'Financials'),
    
    -- Healthcare (3)
    ('JNJ',   'Johnson & Johnson',       'Healthcare'),
    ('UNH',   'UnitedHealth Group',      'Healthcare'),
    ('PFE',   'Pfizer Inc.',             'Healthcare'),
    
    -- Consumer Defensive (3)
    ('WMT',   'Walmart Inc.',            'Consumer Defensive'),
    ('PG',    'Procter & Gamble Co.',    'Consumer Defensive'),
    ('KO',    'Coca-Cola Co.',           'Consumer Defensive'),
    
    -- Energy (1)
    ('XOM',   'Exxon Mobil Corp.',       'Energy')
ON CONFLICT (symbol) DO NOTHING;
