# Báo cáo tiến độ theo tuần

> Sinh viên: Hoàng Văn Nhân. MSSV: 20235542
> Đề tài: **Ứng dụng Agentic AI trong Chứng khoán: Stock Report Agent** (Project 3 → ĐATN)
> Quy ước: tuần mới ở trên, tuần cũ ở dưới. Bản này trùng nội dung với Note trên nhóm Facebook, kèm link chi tiết.

---

## Báo cáo ngày 27/09/2026 (Tuần 1)

**Trao đổi với thầy**
- Thầy giao đề tài và gợi ý tham khảo báo cáo, repo của khóa trước.
- Đồ án theo hướng **ứng dụng**: sản phẩm phải triển khai thật. **Lưu lượng người dùng là tiêu chí quan trọng** khi đánh giá ĐATN.

**Công việc đã làm**
- Đọc mô tả đề tài; đọc báo cáo và mã nguồn của khóa trước ([stock-report-agent-20251](https://github.com/buinguyenkhai/stock-report-agent-20251)).
- Phân tích hệ thống của khóa trước:
  - **Điểm mạnh:** Hybrid OCR (Tesseract + Surya) được đánh giá định lượng (Number F1 85,3%); kiến trúc agent LangGraph rõ ràng.
  - **Hạn chế:**
    - Chưa làm bước phân tích, so sánh và tạo báo cáo có biểu đồ.
    - Mỗi chỉ tiêu chỉ lưu cột "kỳ này", nên chưa so sánh được với cùng kỳ.
    - Chưa dùng CSDL.
    - Mỗi truy vấn mất khoảng 5 phút, cần GPU, chạy local.
- Khảo sát bối cảnh năm 2026:
  - Quy định công bố BCTC: hạn 20 ngày sau quý, công ty mẹ 30 ngày. Vì vậy mùa BCTC Q3 rơi vào khoảng 10–30/10.
  - Các sản phẩm "AI chứng khoán" đã có trên thị trường.
  - Ranh giới pháp lý: không được khuyến nghị mua/bán khi không có giấy phép.
- Khảo sát nhu cầu người dùng: diễn đàn (F319, Voz), đánh giá ứng dụng, cộng đồng quant.

**Kết quả chính**
- **Phát hiện kỹ thuật:** Thông tư 99/2025 thay Thông tư 200 từ BCTC Q1/2026 và đổi một số mã số (ví dụ tổng tài sản 270 → 280). Kiểm tra trên ~940 BCTC Q2/2026 (lấy từ một kho BCTC đã OCR công khai):
  - khoảng 88% đã dùng mã mới, khoảng 11% vẫn ghi mã cũ;
  - khoảng 1/4 dùng dấu phẩy để phân tách hàng nghìn.
  - → Hệ thống phải chuẩn hóa mã số theo phiên bản mẫu biểu, không được hard-code.
- **Nhu cầu nổi bật của người dùng:**
  - phân biệt tin đồn với thông tin chính thức;
  - hiểu nhanh kết quả kinh doanh;
  - theo dõi danh mục ở nhiều CTCK với giá vốn đúng.
- **Hoàn thành bộ tài liệu định hướng** (thư mục [`dinh-huong/`](dinh-huong/)): tầm nhìn và lộ trình, kiến trúc kỹ thuật, nghiên cứu người dùng, tác động của tin tức, kiến thức nền về thị trường.

**Ý tưởng, đề xuất định hướng (xin ý kiến thầy)**
- **Đổi cách làm:** trước đây người dùng hỏi thì agent mới đi tải và OCR. Nay hệ thống đọc mọi BCTC ngay khi công bố, tự kiểm chứng bằng ràng buộc kế toán (ví dụ tổng tài sản = tổng nguồn vốn) rồi lưu CSDL. Nhờ vậy báo cáo trả về trong vài giây.
- **Project 3:**
  - agent phân tích BCTC và radar mùa BCTC Q3/2026 cho nhóm VN30 và các ngân hàng;
  - web có danh sách theo dõi;
  - chạy thật trong hai mùa BCTC Q3 và Q4.
- **ĐATN:** mở rộng thành "đội ngũ AI" quanh danh mục của nhà đầu tư: theo dõi công bố thông tin, giải thích biến động giá, tính lãi/lỗ thật.

**Câu hỏi cho thầy**
1. Hội đồng Project 3 đánh giá nặng phần sản phẩm chạy thật (số liệu người dùng) hay chiều sâu kỹ thuật?
2. Thầy có đồng ý hướng mở rộng sang quản lý danh mục ở ĐATN không?
3. Lab có hỗ trợ API LLM hoặc máy chủ không? Sản phẩm có thể vận hành dưới danh nghĩa dự án của lab không?

**Kế hoạch tuần tới (28/09 – 04/10)**
- Dựng CSDL, module thu thập BCTC từ Vietstock, và pipeline trích xuất bằng VLM (đủ các cột so sánh).
- Thử trích xuất 20 BCTC Q2/2026; đo tỷ lệ vượt kiểm tra cân đối để chọn mô hình.
- Bật thu thập dữ liệu nền: tin tức (kèm giờ đăng), công bố thông tin, giá cuối ngày.
- Hỏi thử ChatGPT/Gemini khoảng 20 câu về số liệu BCTC Q2/2026, rồi đối chiếu với BCTC gốc.

---

## Mẫu cho các tuần sau (copy lên đầu file)

```
## Báo cáo ngày dd/mm/yyyy (Tuần N)

**Trao đổi với thầy:** (góp ý nhận được tuần trước và cách đã xử lý)
**Tiến độ:** (việc đã làm, có số liệu)
**Kết quả / minh chứng:** (link commit, ảnh, video demo, bảng đánh giá)
**Vướng mắc:** (điều chưa làm được, vì sao, dự định xử lý)
**Kế hoạch tuần tới:**
**Câu hỏi cho thầy:** (nếu có)
```
