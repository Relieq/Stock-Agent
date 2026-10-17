-- Ràng buộc giữa hai báo cáo ghi cột dạng "cột trái~cột phải" (ví dụ "ytd_prev_year~ytd_prev_year", 27 ký tự) vượt
-- giới hạn 20 ký tự cũ; mã dòng đặt theo vị trí của ngân hàng (ví dụ "b.fixed_assets.1.1") cũng có thể dài thêm.
ALTER TABLE validations ALTER COLUMN column_kind TYPE varchar(64);
ALTER TABLE line_items ALTER COLUMN code TYPE varchar(64);
