# Báo cáo tiến độ theo tuần

> Sinh viên: Hoàng Văn Nhân. MSSV: 20235542
> Đề tài: **Ứng dụng Agentic AI trong Chứng khoán: Stock Report Agent** (Project 3 → ĐATN)
> Quy ước: tuần mới ở trên, tuần cũ ở dưới. Bản này trùng nội dung với Note trên nhóm Facebook, kèm link chi tiết.

---

## Kế hoạch học kỳ

| Thời gian | Nội dung |
|---|---|
| 28/09 – 11/10 | Dựng CSDL, module thu thập và trích xuất BCTC (bản đầu) |
| 12/10 – 08/11 | Chạy thử trong mùa BCTC quý 3 (VN30 + các ngân hàng) |
| 09/11 – 06/12 | Agent phân tích và tạo báo cáo so sánh; mở rộng lên VN100 |
| 07/12 – 03/01 | Kiểm chứng số liệu, đánh giá độ chính xác |
| 04/01 – 31/01 | Chạy trong mùa BCTC quý 4, viết báo cáo final |

---

## Báo cáo ngày 03/10/2026 (Tuần 2)

> Đã cập nhật kết quả phần CSDL và thu thập (mục **Kết quả**).

Dạ em xin báo cáo tiến độ tuần 2 để thầy nắm ạ:

**Trao đổi với thầy:**
- Thầy góp ý hướng quản lý danh mục chưa có gì đặc biệt cho ĐATN.
- Thầy nêu hai ví dụ ĐATN trước đây: đánh giá báo cáo KQKD có gì bất thường; tìm doanh nghiệp có KQKD tốt theo phương pháp đầu tư tăng trưởng.
- Thầy gợi ý em trải nghiệm sstock.vn.

Em đã trải nghiệm sstock.vn và đề xuất lại hướng ĐATN như dưới đây.

**Về sstock.vn** ([ghi chú chi tiết](khao-sat/sstock.md), [ảnh chụp](https://drive.google.com/drive/folders/1EhRh39TGHEqmDqDVlqXjQnkIAy3GCSt2?usp=sharing)), em đã tìm hiểu:
- **Điểm mạnh** (các chức năng phân tích đều miễn phí):
  - BCTC 17 quý, có mẫu riêng cho ngân hàng;
  - công bố công thức biểu đồ theo mã chỉ tiêu VAS;
  - 7 bộ lọc dựng sẵn, có bộ riêng cho BĐS và chứng khoán;
  - chỉ số sức mạnh tương đối cho cổ phiếu và ngành;
  - AI tóm tắt tin tức.
- **Chưa phát hiện bất thường.** Ví dụ:
  - tăng trưởng do nền thấp: KSF +11.944% (quý 2/2026);
  - lỗ thu hẹp hiển thị như tăng trưởng: NTL quý 4/2025 lỗ 3 tỷ so với lỗ 35 tỷ, hiện +91,3%;
  - FPT quý 1/2026: doanh thu giảm 22,3% so với cùng kỳ; so với quý trước, lãi từ công ty liên doanh, liên kết tăng từ 284 lên 667 tỷ, LNST của cổ đông không kiểm soát giảm từ 485 xuống −11 tỷ. Đây là dấu hiệu thường gặp khi thôi hợp nhất một công ty con, nhưng trang không có chú thích nào.
- **Chưa có sàng lọc theo phương pháp tăng trưởng chuẩn** (CANSLIM, GARP…):
  - chưa giải thích vì sao mã lọt lọc;
  - chưa có backtest;
  - DCL đang lỗ (LNST 4 quý gần nhất −2,26 tỷ) vẫn lọt bộ lọc tăng trưởng.
- **Dữ liệu chỉ có số riêng từng quý:**
  - không có cột cùng kỳ, cột lũy kế;
  - không có thuyết minh dạng dữ liệu;
  - ngày trong kho tài liệu là ngày tải lên, không phải ngày công bố.

**Về các công cụ hiện có và quy trình đầu tư** ([ghi chú chi tiết](khao-sat/tu-dong-hoa-dau-tu.md)), em đã tìm hiểu:
- các công cụ tài chính, chứng khoán trên thế giới và tại Việt Nam;
- quy trình làm việc của một bộ phận đầu tư, bước nào đã được tự động hóa;
- cách giữ con người duyệt trong các hệ thống đầu tư tự động.

**Rút ra:**
- Tỷ lệ tăng trưởng đơn thuần dễ gây hiểu nhầm. Cần tách tăng trưởng từ hoạt động chính khỏi tăng trưởng nhờ khoản bất thường hoặc nhờ nền thấp.
- Nguyên nhân biến động thường nằm trong thuyết minh và công văn giải trình. Vì vậy hệ thống cần đọc được cả văn bản, không chỉ bảng số.
- Muốn đánh giá một bộ lọc trung thực bằng backtest thì phải biết chính xác thông tin được công bố khi nào.
- Các quỹ đầu tư mới dùng AI để nghiên cứu và soạn thảo, quyết định vẫn do con người. Các thử nghiệm để AI tự giao dịch chưa cho kết quả tốt hơn mua và nắm giữ. Vì vậy hệ thống nên đề xuất, còn con người duyệt.

**Đề xuất hướng ĐATN**, gộp hai hướng thầy gợi ý: *Agent phát hiện và giải thích bất thường trong kết quả kinh doanh, ứng dụng sàng lọc doanh nghiệp tăng trưởng.* Gồm ba phần chính và một phần mở rộng:
1. **Phát hiện bất thường** trong mỗi BCTC mới:
   - nền thấp, lỗ thu hẹp;
   - lợi nhuận ngoài hoạt động chính, lợi nhuận không đi kèm dòng tiền;
   - thay đổi phạm vi hợp nhất, chênh lệch sau kiểm toán.
2. **Agent tìm nguyên nhân** trong thuyết minh, công văn giải trình và tin tức. Agent đối chiếu lời giải trình của doanh nghiệp với số liệu, rồi tách ra lợi nhuận cốt lõi. Mọi kết luận có trích dẫn tới trang tài liệu gốc.
3. **Sàng lọc theo phương pháp tăng trưởng** (CANSLIM, GARP…) trên lợi nhuận cốt lõi:
   - mỗi mã có giải thích vì sao lọt lọc;
   - đánh giá bằng backtest trên dữ liệu theo đúng ngày công bố.
4. **Phần mở rộng: hỗ trợ ra quyết định có con người duyệt.** Hệ thống đề xuất theo quy tắc người dùng tự đặt, người dùng quyết định. Thử nghiệm bằng giao dịch giả lập.

Hướng quản lý danh mục em xin bỏ khỏi phần chính.

**Project 3** giữ kế hoạch cũ: đọc và kiểm chứng BCTC ngay khi công bố, lưu CSDL. Khác khóa trước ở chỗ:
- lấy đủ các cột (cùng kỳ, lũy kế);
- tự kiểm tra bằng ràng buộc kế toán;
- xử lý cả mẫu ngân hàng và mẫu mới theo Thông tư 99;
- ghi đúng ngày công bố.

Dữ liệu này chính là nền cho hướng ĐATN trên. Riêng giai đoạn 09/11–06/12, phần agent phân tích sẽ làm thử hai thứ:
- cầu lợi nhuận: lợi nhuận tăng, giảm đến từ dòng nào;
- một số cờ bất thường đơn giản.

**Tiến độ:** tuần này em dành phần lớn thời gian để xem lại hướng ĐATN theo góp ý của thầy. Phần CSDL và module thu thập không phụ thuộc hướng ĐATN nên em đã làm xong bản đầu; phần trích xuất chuyển sang tuần tới; riêng phần agent phân tích em sẽ làm theo ý kiến của thầy về hướng trên.

**Kết quả** ([mã nguồn và cách chạy](../Code/README.md)):
- **CSDL** PostgreSQL chạy bằng Docker, gồm các bảng công ty, tài liệu, file đã tải (mỗi phiên bản file một dòng, không ghi đè khi BCTC công bố lại), số liệu trích xuất và kết quả kiểm chứng.
- **Module thu thập** lấy danh sách BCTC từ Vietstock, nhận dạng từ tiêu đề: loại báo cáo, kỳ, hợp nhất/công ty mẹ, soát xét/kiểm toán, bản điều chỉnh. Bộ nhận dạng được kiểm thử trên toàn bộ 46 dạng tiêu đề thực tế của VN30 năm 2025–2026.
- **Chạy thật năm 2026 cho VN30:** 174 tài liệu, nhận dạng đúng 174/174. **30/30 mã đã có BCTC quý 2/2026** (58 file, 487 MB), danh sách ở [Data/bctc_q2_2026_vn30.csv](../Data/bctc_q2_2026_vn30.csv). Chạy lại không tạo dữ liệu trùng.
- **Phát hiện:**
  - Ngày giờ trên Vietstock là giờ Vietstock tải lên, không phải giờ công bố: BID, MBB, SSB, STB có cùng mốc 31/07/2026 11:35. Cần lấy giờ công bố từ HOSE/HNX hoặc cổng CBTT để tính đúng thời điểm.
  - 5/58 file là `.zip` (SSI, TCX, VPB), bước trích xuất phải giải nén.
  - VNM công bố BCTC quý đã soát xét; LPB và TCX chỉ có một báo cáo (không có công ty con).

**Kế hoạch tuần tới:**
- Pipeline trích xuất (đủ các cột, kiểm tra bằng ràng buộc kế toán).
- Chạy thử trên 20 BCTC Q2/2026 để kịp mùa BCTC quý 3 (từ khoảng 12/10).
- Rà thêm các sản phẩm khác (Vietstock, FireAnt, Simplize, Index AI) để khẳng định điểm mới của hướng ĐATN.

**Câu hỏi cho thầy:** thầy thấy hướng ĐATN trên có phù hợp không ạ?

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

**Rút ra:**
- OCR mới đạt Number F1 ~85%, nên cần thêm bước kiểm chứng số bằng ràng buộc kế toán (VD: tổng tài sản = tổng nguồn vốn).
- Hệ thống cũ chỉ lưu 1 cột số cho mỗi chỉ tiêu nên không so sánh được với cùng kỳ, cần lưu đủ các cột.
- Từ 2026 mẫu BCTC đổi mã số (tổng tài sản 270 → 280; khoảng 11% BCTC Q2/2026 vẫn ghi mã cũ), cần chuẩn hóa mã theo phiên bản mẫu.

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
