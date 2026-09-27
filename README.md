# Stock-Agent

Đề tài Project 3 → ĐATN: **Ứng dụng Agentic AI trong Chứng khoán: Stock Report Agent**.

Tầm nhìn (tên tạm **"Soi"**): lớp sự thật thời gian thực của thị trường vốn Việt Nam.
- Mọi công bố thông tin được AI đọc, kiểm chứng và giải thích trong vài phút, có trích nguồn đến từng con số. Bắt đầu từ BCTC, sau đó đến giao dịch nội bộ, cổ tức, ĐHCĐ, trái phiếu…
- Phục vụ người dùng qua web và Zalo, đồng thời chạy **bên trong ChatGPT và các trợ lý AI khác** qua MCP.
- Miễn phí, trung lập; là dịch vụ thông tin, không phải tư vấn đầu tư.

**Tại sao không hỏi thẳng ChatGPT?** ChatGPT chỉ trả lời khi được hỏi, không có dữ liệu Việt Nam đã chuẩn hóa, và không chứng minh được con số. Soi canh thị trường 24/7, có dữ liệu đã kiểm chứng, và đưa chính dữ liệu đó vào ChatGPT. Xem [mục 1 của tài liệu định hướng](docs/vision-and-roadmap.md#1-câu-hỏi-chốt-tại-sao-không-hỏi-thẳng-chatgpt).

## Tài liệu định hướng

- [docs/vision-and-roadmap.md](docs/vision-and-roadmap.md): nội dung gồm
  - phân tích đề tài và repo khóa trước;
  - bối cảnh thị trường, đối thủ, pháp lý năm 2026;
  - kho ý tưởng lớn;
  - lộ trình Project 3 → ĐATN;
  - chỉ tiêu người dùng;
  - rủi ro.
- [docs/architecture.md](docs/architecture.md): nội dung gồm
  - kiến trúc kỹ thuật;
  - pipeline đọc và kiểm chứng BCTC (TT200/TT99, ngân hàng, …);
  - mô hình dữ liệu;
  - AI Analyst agent;
  - kế hoạch đánh giá.

## Tham khảo

- Repo khóa trước: [buinguyenkhai/stock-report-agent-20251](https://github.com/buinguyenkhai/stock-report-agent-20251) (MIT). Đóng góp chính là Hybrid OCR (Tesseract + Surya) và bộ benchmark trên dataset vnpdf.
