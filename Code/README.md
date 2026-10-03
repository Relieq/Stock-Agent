# Code

Mã nguồn của dự án. Cấu trúc theo [kiến trúc kỹ thuật](../Baocao/dinh-huong/architecture.md#14-cấu-trúc-repo-đề-xuất).

| Thư mục | Nội dung | Trạng thái |
|---|---|---|
| `infra/` | Docker Compose: PostgreSQL 16 + pgvector | Có |
| `db/migrations/` | Lược đồ CSDL (file `.sql`, áp dụng theo thứ tự tên) | Có |
| `db/seeds/` | Danh sách công ty (VN30) | Có |
| `services/ingestion/` | Thu thập BCTC: lấy danh sách từ Vietstock, nhận dạng tiêu đề, tải file | Có |
| `services/extraction/` | Đọc và kiểm chứng BCTC: chọn PDF, định vị trang, chép bảng bằng mô hình đọc ảnh, chuẩn hóa số, kiểm tra ràng buộc kế toán | Bản đầu; đã chạy thật trên 4 BCTC |
| `services/llm.py` | Gọi mô hình qua giao diện kiểu OpenAI (Gemini, OpenAI, OpenRouter, Ollama) | Có |
| `eval/` | Chấm kết quả trích xuất với bộ duyệt tay (`Data/golden/`) | Có |
| `services/analyst/`, `services/news/`, `apps/web/`, `eval/` | Phân tích, tin tức, giao diện, đánh giá | Sau |

## Cài đặt

Cần Python 3.12 và Docker Desktop.

```bash
cd Code
python -m venv .venv
.venv\Scripts\activate          # Windows; Linux/macOS: source .venv/bin/activate
pip install -e ".[dev]"
copy .env.example .env          # Linux/macOS: cp .env.example .env

docker compose -f infra/docker-compose.yml up -d   # PostgreSQL ở cổng 5433
```

## Thu thập BCTC

```bash
python -m services.ingestion migrate                     # tạo/cập nhật bảng
python -m services.ingestion seed                        # ghi danh sách VN30
python -m services.ingestion discover --year 2026        # lấy danh sách BCTC từ Vietstock
python -m services.ingestion report --year 2026 --period Q2 --csv ../Data/bctc_q2_2026_vn30.csv
python -m services.ingestion download --year 2026 --period Q2   # tải file về ../Data/raw/
```

- Các lệnh chạy lại nhiều lần không tạo dữ liệu trùng: tài liệu khóa theo mã tài liệu của nguồn, file khóa theo SHA-256.
- File tải về nằm trong `Data/raw/` (không đưa lên GitHub).
- `--tickers FPT,VCB` để chỉ chạy một số mã; `--delay` để chỉnh thời gian nghỉ giữa các request (mặc định 1 giây).

## Đọc và kiểm chứng BCTC

Cần API key của một nhà cung cấp mô hình trong `.env` (xem `.env.example`).

```bash
python -m services.llm                                            # kiểm tra key, liệt kê mô hình dùng được
python -m services.extraction run --tickers FPT --year 2026 --period Q2 --scope consolidated
python -m services.extraction show --doc-id 28                    # các ràng buộc bị lệch
python -m services.extraction reread --doc-id 28                  # đọc lại các ô thuộc ràng buộc bị lệch
python -m services.extraction recheck --doc-id 28                 # kiểm tra lại từ kết quả đã lưu (khi sửa rules.py), không gọi mô hình
python eval/golden.py                                             # chấm với bộ duyệt tay
```

- Mô hình chỉ định vị trang và chép nguyên văn các ô; đổi chuỗi thành số, đổi đơn vị, kiểm tra cộng tổng đều bằng code.
- Ràng buộc kế toán khai báo theo mẫu trong `services/extraction/rules.py`: TT200 đầy đủ; TT99 mới có các dòng tổng;
  ngân hàng và công ty chứng khoán chưa có. Mẫu (TT200/TT99) nhận dạng bằng phép cộng kiểm tra, không suy từ năm.
- Kết quả từng tài liệu lưu ở `Data/raw/extracted/<mã>/<id>_<sha>.json` và trong bảng `line_items`, `validations`.
- Ràng buộc bắt buộc bị lệch thì đọc lại đúng các ô liên quan ở độ phân giải cao hơn, **không** cho mô hình biết
  con số mong đợi (để mô hình không "sửa cho khớp"); mọi lần đọc lại được ghi lại cả giá trị trước và sau.
- Trang in xoay ngang được nhận ra ở bước định vị trang và xoay thẳng trước khi chép bảng.
- Quy ước dấu (chi phí in số dương hay số âm trong ngoặc) được nhận ra theo từng tài liệu.
- Mã số in trùng trên chính BCTC được ghi lại (`duplicate_codes`) thay vì để dòng sau đè dòng trước.
- Chưa làm: ràng buộc cho ngân hàng và công ty chứng khoán; đọc lại bằng mô hình mạnh hơn khi đọc lại lần đầu vẫn lệch.

Kết quả thử với `gpt-5.4-mini` trên BCTC hợp nhất quý 2/2026 (03/10/2026):

| Mã | Mẫu nhận dạng | Ràng buộc bắt buộc | Ghi chú |
|---|---|---|---|
| FPT | TT99 | 32/32 | Đọc sai 1 chữ số ở doanh thu thuần quý; ràng buộc khoanh đúng ô, đọc lại sửa đúng (đã đối chiếu ảnh gốc) |
| HPG | TT99 (in mã tổng tài sản 270) | 32/32 | BCTC tự in trùng mã 230 cho tài sản sinh học dài hạn và BĐS đầu tư |
| MWG | TT99 | 34/34 | Trang KQKD in xoay ngang; chi phí in số âm |
| VNM | TT99 | 32/32 | |

Trung bình khoảng 50 nghìn token vào và 12 nghìn token ra cho mỗi BCTC (khoảng 0,09 USD với giá ngày 03/10/2026).

## Kiểm thử

```bash
python -m pytest                                 # toàn bộ
python -m pytest tests/test_titles.py -k parse   # một nhóm test
```

## Ghi chú về dữ liệu

- `source_listed_at` là thời điểm Vietstock đăng hoặc cập nhật tài liệu, **không phải** thời điểm công bố chính thức. Nhiều ngân hàng có cùng một mốc giờ (ví dụ BID, MBB, SSB, STB cùng 31/07/2026 11:35), cho thấy đây là giờ Vietstock tải lên hàng loạt. Thời điểm công bố chính thức (`published_at`) sẽ lấy từ HOSE/HNX hoặc cổng CBTT của UBCKNN.
- Một số tài liệu là file `.zip` (quý 2/2026: 5/58 file, của SSI, TCX, VPB), cần giải nén ở bước trích xuất.
- Logic gọi danh sách tài liệu Vietstock dựa trên repo khóa trước [stock-report-agent-20251](https://github.com/buinguyenkhai/stock-report-agent-20251) (giấy phép MIT).
