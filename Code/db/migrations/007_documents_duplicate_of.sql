-- Hai công bố khác nhau mà cùng một file (cùng mã băm SHA-256), ví dụ Vietstock đăng BCTC bán niên 2026 của GVR hai lần
-- (29/8 và 3/9). Bản sau trỏ về bản đầu và không đọc lại: đỡ tiền gọi mô hình, không đếm trùng khi thống kê.
ALTER TABLE documents ADD COLUMN duplicate_of BIGINT REFERENCES documents(id);
