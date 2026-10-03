# Code

Mã nguồn của dự án. Cấu trúc theo [kiến trúc kỹ thuật](../Baocao/dinh-huong/architecture.md#14-cấu-trúc-repo-đề-xuất).

| Thư mục | Nội dung | Trạng thái |
|---|---|---|
| `infra/` | Docker Compose: PostgreSQL 16 + pgvector | Có |
| `db/migrations/` | Lược đồ CSDL (file `.sql`, áp dụng theo thứ tự tên) | Có |
| `db/seeds/` | Danh sách công ty (VN30) | Có |
| `services/ingestion/` | Thu thập BCTC: lấy danh sách từ Vietstock, nhận dạng tiêu đề, tải file | Có |
| `services/extraction/` | Đọc và kiểm chứng BCTC | Tuần tới |
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

## Kiểm thử

```bash
python -m pytest                                 # toàn bộ
python -m pytest tests/test_titles.py -k parse   # một nhóm test
```

## Ghi chú về dữ liệu

- `source_listed_at` là thời điểm Vietstock đăng hoặc cập nhật tài liệu, **không phải** thời điểm công bố chính thức. Nhiều ngân hàng có cùng một mốc giờ (ví dụ BID, MBB, SSB, STB cùng 31/07/2026 11:35), cho thấy đây là giờ Vietstock tải lên hàng loạt. Thời điểm công bố chính thức (`published_at`) sẽ lấy từ HOSE/HNX hoặc cổng CBTT của UBCKNN.
- Một số tài liệu là file `.zip` (quý 2/2026: 5/58 file, của SSI, TCX, VPB), cần giải nén ở bước trích xuất.
- Logic gọi danh sách tài liệu Vietstock dựa trên repo khóa trước [stock-report-agent-20251](https://github.com/buinguyenkhai/stock-report-agent-20251) (giấy phép MIT).
