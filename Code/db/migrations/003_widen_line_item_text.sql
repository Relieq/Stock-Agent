-- Cột thuyết minh có thể chứa nhiều số hoặc cả công thức (ví dụ "26, 28" hay "{30 = 20 + (21 - 22) - (25 + 26)}")
ALTER TABLE line_items ALTER COLUMN note_ref TYPE TEXT;
ALTER TABLE line_items ALTER COLUMN code TYPE VARCHAR(20);
