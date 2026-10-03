-- Giữ chuỗi số đúng như in trên BCTC bên cạnh giá trị đã quy đổi, để truy vết và chấm điểm với bộ duyệt tay.
ALTER TABLE line_items ADD COLUMN value_raw TEXT;
