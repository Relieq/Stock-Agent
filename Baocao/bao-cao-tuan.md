# Báo cáo tiến độ theo tuần

> Sinh viên: Hoàng Văn Nhân. MSSV: 20235542
> Đề tài: **Ứng dụng Agentic AI trong Chứng khoán: Stock Report Agent** (Project 3 → ĐATN)
> Quy ước: tuần mới ở trên, tuần cũ ở dưới. Bản này trùng nội dung với Note trên nhóm Facebook, kèm link chi tiết.

---

## Báo cáo ngày 27/09/2026 (Tuần 1)

Dạ em xin báo cáo tiến độ tuần 1 để thầy nắm ạ:

**Về hệ thống của khóa trước** (repo [stock-report-agent-20251](https://github.com/buinguyenkhai/stock-report-agent-20251)), em đã tìm hiểu:
- Pipeline agent LangGraph:
  - process_query: LLM few-shot → ReportRequest (mã, năm, kỳ, hợp nhất/riêng); lọc kỳ chưa công bố.
  - extract_report_link: gọi API getdocument của Vietstock, không dùng LLM.
  - ocr_report: Hybrid OCR.
  - parse_report: 4 extractor BS/PL/CF/metadata chạy song song → AggregatedParser dùng Pydantic structured output.
  - generate_final_response: hiện chỉ trả link.
- Hybrid OCR: Tesseract (có confidence từng từ) → chọn ô có confidence thấp (ô số < 0,95, ô chữ < 0,35) hoặc số đáng ngờ → crop → Surya đọc lại theo batch → kiểm tra trước khi nhận (tỷ lệ độ dài, LCS, giữ tính chất số, số chữ số hợp lý) → merge. Kèm sửa ký tự dễ nhầm (O→0, l→1…) và suy luận vùng bảng. Kết quả trên 401 trang: Number F1 81,6% (Tesseract) → 85,3% (Hybrid) → 87,8% (Marker); tốc độ 7,8 → 11,1 → 58,3 s/trang.
- Hạn chế:
  - Schema chỉ có một `value` cho mỗi chỉ tiêu (cột kỳ này, `services/parser.py`) → mất cột cùng kỳ và lũy kế → không so sánh YoY được.
  - Bước phân tích và tạo báo cáo chưa làm.
  - Có `schema.sql` nhưng code chưa dùng.
  - Khoảng 5 phút mỗi báo cáo (OCR 194 s + LLM 102 s), cần GPU.

**Về BCTC Việt Nam**, em đã tìm hiểu:
- Cấu trúc 3 báo cáo và các cột số liệu:
  - KQKD quý: quý này, cùng kỳ, lũy kế.
  - BCĐKT: cuối kỳ, đầu năm.
  - LCTT: lũy kế, nên số riêng quý = lũy kế kỳ này − lũy kế kỳ trước.
- Hệ thống mã số và các ràng buộc kế toán dùng để tự kiểm chứng: 270 = 100 + 200, 270 = 440, 60 = 50 − 51 − 52, tiền cuối kỳ trên LCTT = tiền trên BCĐKT.
- Thông tư 99/2025 thay Thông tư 200 từ 1/1/2026: thêm dòng tài sản sinh học → dịch mã (tổng tài sản 270 → 280; mã 270 giờ là tài sản dài hạn khác). Ngân hàng, CTCK, bảo hiểm dùng mẫu riêng. Em kiểm tra trên khoảng 940 BCTC Q2/2026: khoảng 88% ghi mã 280, 11% vẫn ghi 270; khoảng 25% dùng dấu phẩy phân tách hàng nghìn → cần nhận diện phiên bản mẫu, chuẩn hóa mã số, và suy dấu phân cách theo từng tài liệu.
- Quy định công bố thông tin: BCTC quý nộp trong 20 ngày (công ty mẹ 30 ngày) → mùa BCTC Q3 rơi vào khoảng 10–30/10.

**Định hướng:** đọc và kiểm chứng BCTC ngay khi công bố rồi lưu CSDL, thay vì đợi người dùng hỏi mới OCR; chạy thật trong mùa BCTC Q3.

**Kế hoạch tuần tới:** dựng CSDL, module thu thập và pipeline trích xuất (đủ các cột); chạy thử trên 20 BCTC Q2/2026.

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
