# Bộ BCTC duyệt tay (golden set)

Số liệu nhập tay từ PDF gốc, dùng để đo độ chính xác của pipeline trích xuất và để so sánh các mô hình.

## Bộ quý 2/2026 (`golden_q2_2026.csv`)

5 BCTC hợp nhất: FPT, HPG, MWG, VNM (doanh nghiệp thường) và VCB (ngân hàng). Mỗi dòng là một ô số cần đọc:
các dòng tổng và chỉ tiêu chính của bảng cân đối, KQKD và lưu chuyển tiền tệ, ở tất cả các cột.

Cách nhập (mở PDF trong `Data/raw/vietstock/<mã>/2026/`):
- `code_as_printed`: mã số **đúng như in** trên BCTC. Cột `code_hint` chỉ là gợi ý theo mẫu cũ (TT200); từ 2026 một
  số mã đã đổi theo TT99, ví dụ tổng tài sản là 280 thay vì 270. Ngân hàng không có mã số thì để trống.
- `value_as_printed`: chuỗi số **đúng như in**, giữ nguyên dấu chấm, dấu phẩy, dấu ngoặc. Ô trống hoặc "-" thì ghi `-`.
- `page`: số trang trong file PDF (theo trình đọc PDF, không phải số in ở chân trang).
- `ghi_chu`: điều đáng chú ý, ví dụ "không có dòng này", "số bị mờ".

Nên tự đọc từ PDF, **không** chép từ kết quả của mô hình rồi sửa: người duyệt dễ bị kết quả có sẵn dẫn dắt,
làm bộ duyệt tay mất giá trị.

Chấm điểm: từ thư mục `Code/`, chạy `python eval/golden.py`.
