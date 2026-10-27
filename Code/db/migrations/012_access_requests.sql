-- Xin dùng thử từ trang giới thiệu (khách chưa có tài khoản): quản trị xem ở /quan-tri và bấm mời.
CREATE TABLE access_requests (
    id          BIGSERIAL PRIMARY KEY,
    email       TEXT NOT NULL CHECK (length(email) BETWEEN 3 AND 254),
    note        TEXT NOT NULL DEFAULT '' CHECK (length(note) <= 500),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    invited_at  TIMESTAMPTZ
);
CREATE INDEX access_requests_email_idx ON access_requests (email, created_at DESC);
CREATE INDEX access_requests_created_idx ON access_requests (created_at DESC);
