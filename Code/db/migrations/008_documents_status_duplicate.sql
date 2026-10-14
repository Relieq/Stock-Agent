-- Thêm trạng thái 'duplicate' (công bố trùng file với công bố khác, xem 007)
ALTER TABLE documents DROP CONSTRAINT documents_status_check;
ALTER TABLE documents ADD CONSTRAINT documents_status_check CHECK (status IN
    ('discovered', 'downloaded', 'extracting', 'verified', 'needs_review', 'approved', 'failed', 'skipped', 'duplicate'));
