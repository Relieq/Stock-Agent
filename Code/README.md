# Code

Mã nguồn của dự án. Sẽ bắt đầu từ tuần 2 (28/09/2026).

Cấu trúc dự kiến (chi tiết ở [kiến trúc kỹ thuật](../Baocao/dinh-huong/architecture.md#14-cấu-trúc-repo-đề-xuất)):
- `services/ingestion/`: thu thập BCTC và công bố thông tin.
- `services/extraction/`: đọc và kiểm chứng BCTC.
- `services/analyst/`: AI Analyst.
- `services/news/`: thu thập tin tức (chạy nền).
- `apps/web/`: giao diện web.
- `eval/`: đánh giá (benchmark, golden set, "ChatGPT test").
