-- Thời điểm pipeline xử lý xong tài liệu, để đo thời gian từ lúc phát hiện / nguồn đăng tới lúc có kết quả
ALTER TABLE documents ADD COLUMN processed_at TIMESTAMPTZ;
