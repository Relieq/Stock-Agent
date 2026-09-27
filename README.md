# Stock-Agent

Đề tài Project 3 → ĐATN: **Ứng dụng Agentic AI trong Chứng khoán: Stock Report Agent**.

Tầm nhìn (tên tạm **"Soi"**): **đội ngũ đầu tư AI của riêng bạn**, làm việc quanh danh mục của bạn.
- **Nền móng:** mọi công bố thông tin (BCTC, giao dịch nội bộ, cổ tức, ĐHCĐ…) được AI đọc, kiểm chứng và giải thích trong vài phút, có trích nguồn đến từng con số.
- **Đội ngũ gồm:** chuyên viên phân tích BCTC (đề tài gốc), chuyên viên tin tức & sự kiện, kế toán danh mục, quản trị rủi ro, người giải thích "vì sao giá biến động", thư ký soạn bản tin mỗi sáng.
- **Kênh:** ứng dụng riêng (web, Zalo). MCP để sau.
- **Nguyên tắc:** miễn phí, trung lập; là dịch vụ thông tin, không phải tư vấn đầu tư; không quyết định thay người dùng.

**Tại sao không hỏi thẳng ChatGPT?** ChatGPT chỉ trả lời khi được hỏi, không biết danh mục của bạn, không có dữ liệu Việt Nam đã chuẩn hóa, và không chứng minh được con số. Xem [mục 1 của tài liệu định hướng](docs/vision-and-roadmap.md#1-câu-hỏi-chốt-tại-sao-không-hỏi-thẳng-chatgpt).

## Tài liệu định hướng

Nên đọc theo thứ tự:
1. [docs/north-star.md](docs/north-star.md): đích đến dài hạn, gồm đội ngũ đầu tư AI và danh mục ở trung tâm; ranh giới pháp lý; kỳ vọng thực tế.
2. [docs/user-research.md](docs/user-research.md): người dùng thực sự cần gì, tổng hợp từ diễn đàn, đánh giá ứng dụng và cộng đồng quant.
3. [docs/news-impact.md](docs/news-impact.md): tin tức tác động tới giá ra sao, cái gì làm được và cái gì không nên làm.
4. [docs/market-primer.md](docs/market-primer.md): kiến thức nền về thị trường Việt Nam cho người làm sản phẩm.

Chi tiết:
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
