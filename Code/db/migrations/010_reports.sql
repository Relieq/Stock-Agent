-- Báo cáo do agent tạo theo yêu cầu người dùng (Baocao/dinh-huong/agent-bao-cao.md mục 9). Trạng thái giữa chừng của
-- đồ thị nằm trong các bảng checkpoint của LangGraph (tạo bằng PostgresSaver.setup() trong lệnh migrate).
CREATE TABLE reports (
    id            BIGSERIAL PRIMARY KEY,
    user_id       BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    question      TEXT NOT NULL,
    status        VARCHAR(24) NOT NULL DEFAULT 'planning'
                  CHECK (status IN ('planning', 'needs_clarification', 'awaiting_confirmation', 'waiting_data',
                                    'writing', 'done', 'failed')),
    plan          JSONB,
    notes         JSONB,
    question_back TEXT,
    missing       JSONB,                 -- BCTC còn thiếu đề nghị đọc thêm
    request_ids   BIGINT[],              -- processing_requests đã tạo khi người dùng xác nhận
    sources       JSONB,                 -- BCTC nguồn kèm phiên bản kết quả trích xuất
    charts        JSONB,
    sheet         JSONB,                 -- bảng số (dòng S...)
    result        JSONB,                 -- {draft, links}
    guard_log     JSONB,                 -- nhật ký kiểm số: các lần viết, câu bị bỏ
    usage         JSONB,                 -- chi phí gọi mô hình theo bước
    plan_key      TEXT,
    sources_key   TEXT,
    reused_from   BIGINT REFERENCES reports(id),
    error         TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at   TIMESTAMPTZ
);
CREATE INDEX reports_user_idx ON reports (user_id, created_at DESC);
CREATE INDEX reports_status_idx ON reports (status);
