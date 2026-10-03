-- Lược đồ ban đầu: công ty, tài liệu công bố, file tải về, số liệu trích xuất, kết quả kiểm chứng.
-- Thiết kế theo Baocao/dinh-huong/architecture.md mục 5, có chỉnh:
--   * tách documents (một tài liệu do nguồn liệt kê) khỏi document_files (từng phiên bản file đã tải),
--     để BCTC công bố lại không ghi đè dữ liệu cũ;
--   * tách thời điểm nguồn đăng tài liệu (source_listed_at) khỏi thời điểm công bố chính thức (published_at).

CREATE TABLE companies (
  ticker        VARCHAR(10) PRIMARY KEY,
  name          TEXT NOT NULL,
  exchange      VARCHAR(10),            -- HOSE / HNX / UPCOM
  industry_code VARCHAR(20),            -- ICB, bổ sung sau
  template      VARCHAR(20) NOT NULL    -- corporate / bank / securities / insurance
    CHECK (template IN ('corporate', 'bank', 'securities', 'insurance'))
);

-- Một dòng = một tài liệu do nguồn liệt kê (ví dụ một mục trong danh sách tài liệu của Vietstock)
CREATE TABLE documents (
  id               BIGSERIAL PRIMARY KEY,
  ticker           VARCHAR(10) NOT NULL REFERENCES companies,
  source           VARCHAR(20) NOT NULL,   -- vietstock / ...
  source_doc_id    VARCHAR(40) NOT NULL,   -- mã tài liệu phía nguồn (Vietstock: FileInfoID)
  source_url       TEXT NOT NULL,
  title_raw        TEXT NOT NULL,
  file_ext         VARCHAR(10),            -- pdf / zip / ...

  -- Các trường nhận dạng từ tiêu đề (services/ingestion/titles.py); NULL nếu không nhận dạng được
  content_kind     VARCHAR(20),   -- full / income_statement / cash_flow / notes
  doc_type         VARCHAR(20),   -- fs_quarter / fs_semiannual / fs_9m / fs_annual
  fiscal_year      INT,
  fiscal_period    VARCHAR(4),    -- Q1..Q4 / H1 / 9M / FY
  scope            VARCHAR(12),   -- consolidated / separate / standalone (công ty không có công ty con)
  audit_status     VARCHAR(12),   -- none / reviewed / audited
  is_amended       BOOLEAN NOT NULL DEFAULT FALSE,  -- tiêu đề có "(điều chỉnh)"
  template_ver     VARCHAR(12),   -- TT200 / TT99 / TCTD / CTCK / BH: nhận dạng từ nội dung ở bước trích xuất

  -- Thời gian (point-in-time)
  source_listed_at TIMESTAMPTZ,   -- thời điểm nguồn đăng/cập nhật tài liệu (Vietstock: LastUpdate), không phải ngày công bố chính thức
  published_at     TIMESTAMPTZ,   -- thời điểm công bố chính thức (HOSE/HNX/UBCKNN), bổ sung khi có nguồn
  discovered_at    TIMESTAMPTZ NOT NULL DEFAULT now(),  -- lần đầu hệ thống thấy tài liệu
  last_seen_at     TIMESTAMPTZ NOT NULL DEFAULT now(),  -- lần gần nhất thấy trong danh sách của nguồn

  status           VARCHAR(20) NOT NULL DEFAULT 'discovered'
    CHECK (status IN ('discovered', 'downloaded', 'extracting', 'verified', 'needs_review', 'failed', 'skipped')),

  UNIQUE (source, source_doc_id)
);

CREATE INDEX documents_period_idx ON documents (fiscal_year, fiscal_period, doc_type);
CREATE INDEX documents_ticker_idx ON documents (ticker);

-- Một dòng = một phiên bản file đã tải. Nội dung đổi (hash khác) thì thêm dòng mới, không ghi đè.
CREATE TABLE document_files (
  id            BIGSERIAL PRIMARY KEY,
  document_id   BIGINT NOT NULL REFERENCES documents ON DELETE CASCADE,
  sha256        CHAR(64) NOT NULL,
  size_bytes    BIGINT NOT NULL,
  storage_key   TEXT NOT NULL,          -- đường dẫn tương đối trong thư mục dữ liệu thô
  source_url    TEXT NOT NULL,          -- URL lúc tải (nguồn có thể đổi tham số ?ver=)
  downloaded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (document_id, sha256)
);

CREATE INDEX document_files_sha256_idx ON document_files (sha256);

-- Một dòng = một ô số trong BCTC
CREATE TABLE line_items (
  id            BIGSERIAL PRIMARY KEY,
  file_id       BIGINT NOT NULL REFERENCES document_files ON DELETE CASCADE,
  statement     VARCHAR(3) NOT NULL,   -- BS / IS / CF
  code          VARCHAR(10),           -- mã số in trên BCTC
  canonical     VARCHAR(40),           -- mã chuẩn hóa nội bộ (theo mẫu + phiên bản)
  label_raw     TEXT,
  note_ref      VARCHAR(20),           -- cột thuyết minh
  column_kind   VARCHAR(20) NOT NULL,  -- q_cur / q_prev_year / ytd_cur / ytd_prev_year / end_period / begin_year
  value         NUMERIC(24, 2),        -- đã quy đổi về đồng
  page          INT,
  bbox          JSONB,
  confidence    REAL,
  method        VARCHAR(30),           -- text_layer / vlm / ocr / manual
  pipeline_ver  VARCHAR(20) NOT NULL
);

CREATE INDEX line_items_file_idx ON line_items (file_id, statement);

-- Kết quả kiểm chứng ràng buộc kế toán
CREATE TABLE validations (
  id           BIGSERIAL PRIMARY KEY,
  file_id      BIGINT NOT NULL REFERENCES document_files ON DELETE CASCADE,
  rule_id      VARCHAR(40) NOT NULL,
  column_kind  VARCHAR(20),
  passed       BOOLEAN NOT NULL,
  lhs          NUMERIC,
  rhs          NUMERIC,
  details      JSONB,
  pipeline_ver VARCHAR(20) NOT NULL,
  checked_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
