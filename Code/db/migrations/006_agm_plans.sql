-- Kế hoạch kinh doanh năm do ĐHCĐ thông qua, để thẻ KQKD tính lũy kế đạt bao nhiêu % kế hoạch (kế hoạch MVP mục 2.1).
-- Nhập tay từ nghị quyết/tài liệu ĐHCĐ: db/seeds/agm_plans_2026.csv, nạp bằng python -m services.metrics plans.
CREATE TABLE agm_plans (
    ticker      VARCHAR(10) NOT NULL REFERENCES companies(ticker),
    fiscal_year INTEGER NOT NULL,
    metric      VARCHAR(20) NOT NULL CHECK (metric IN ('revenue', 'toi', 'pbt', 'npat', 'npat_parent')),
    value       NUMERIC(24, 2) NOT NULL,           -- đồng
    source_url  TEXT NOT NULL,                     -- nghị quyết hoặc tài liệu ĐHCĐ
    note        TEXT,
    PRIMARY KEY (ticker, fiscal_year, metric)
);
