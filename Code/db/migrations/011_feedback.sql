-- Góp ý của người dùng gửi từ chân trang web (đợt người dùng thử): lưu kèm trang đang xem, quản trị xem ở /quan-tri/gop-y.
CREATE TABLE feedback (
    id          BIGSERIAL PRIMARY KEY,
    user_id     BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    page        TEXT NOT NULL DEFAULT '/',
    message     TEXT NOT NULL CHECK (length(message) BETWEEN 1 AND 2000),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX feedback_created_idx ON feedback (created_at DESC);
