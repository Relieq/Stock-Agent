-- Người dùng (chỉ vào được bằng lời mời), đăng nhập bằng link gửi qua email, danh sách theo dõi, email đã gửi,
-- yêu cầu đọc BCTC ngoài danh sách và file người dùng tải lên (kế hoạch MVP mục 2.3-2.6).

CREATE TABLE users (
    id            BIGSERIAL PRIMARY KEY,
    email         TEXT NOT NULL UNIQUE,
    role          VARCHAR(10) NOT NULL DEFAULT 'user' CHECK (role IN ('user', 'admin')),
    daily_quota   INTEGER NOT NULL DEFAULT 3,        -- số BCTC mới được yêu cầu đọc mỗi ngày
    invited_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_login_at TIMESTAMPTZ
);

-- Chỉ lưu mã băm SHA-256 của token, không lưu token
CREATE TABLE login_tokens (
    token_hash CHAR(64) PRIMARY KEY,
    user_id    BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at TIMESTAMPTZ NOT NULL,
    used_at    TIMESTAMPTZ
);

CREATE TABLE sessions (
    token_hash CHAR(64) PRIMARY KEY,
    user_id    BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE watchlist (
    user_id  BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    ticker   VARCHAR(10) NOT NULL REFERENCES companies(ticker),
    added_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, ticker)
);

-- Mỗi BCTC chỉ gửi một email cho mỗi người theo dõi
CREATE TABLE notifications (
    user_id     BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    document_id BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    channel     VARCHAR(10) NOT NULL DEFAULT 'email',
    sent_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    delivered   BOOLEAN NOT NULL,                     -- false: chưa cấu hình SMTP, chỉ in ra
    PRIMARY KEY (user_id, document_id, channel)
);

-- Công ty chủ động theo dõi (VN30) hay chỉ đọc khi có người yêu cầu
ALTER TABLE companies ADD COLUMN tracked BOOLEAN NOT NULL DEFAULT true;

-- BCTC do người dùng tải lên mà không tìm được bản chính thức: chỉ người đó xem
ALTER TABLE documents ADD COLUMN owner_user_id BIGINT REFERENCES users(id);

-- Người duyệt đã đối chiếu ảnh gốc và cho xuất bản
ALTER TABLE documents DROP CONSTRAINT documents_status_check;
ALTER TABLE documents ADD CONSTRAINT documents_status_check CHECK (status IN
    ('discovered', 'downloaded', 'extracting', 'verified', 'needs_review', 'approved', 'failed', 'skipped'));
ALTER TABLE documents ADD COLUMN reviewed_by BIGINT REFERENCES users(id);
ALTER TABLE documents ADD COLUMN reviewed_at TIMESTAMPTZ;

CREATE TABLE processing_requests (
    id          BIGSERIAL PRIMARY KEY,
    user_id     BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind        VARCHAR(10) NOT NULL CHECK (kind IN ('ticker', 'upload')),
    ticker      VARCHAR(10),
    fiscal_year INTEGER,
    fiscal_period VARCHAR(4),
    upload_sha256 CHAR(64),
    upload_key  TEXT,                                 -- đường dẫn file tải lên, tương đối so với RAW_DATA_DIR
    document_id BIGINT REFERENCES documents(id),
    status      VARCHAR(12) NOT NULL DEFAULT 'queued'
                CHECK (status IN ('queued', 'processing', 'done', 'failed', 'rejected')),
    note        TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ
);
CREATE INDEX processing_requests_status_idx ON processing_requests (status, created_at);
