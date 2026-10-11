# Kế hoạch MVP: mùa BCTC quý 3/2026

> Lập ngày 11/10/2026. Thầy hướng dẫn chưa phản hồi về hướng ĐATN, nên từ nay dự án tự chủ trương; tài liệu này là mốc để bám theo và để báo cáo lại.
> Tài liệu liên quan:
> - Nhu cầu người dùng nói chung: [user-research.md](user-research.md)
> - Kiến trúc: [architecture.md](architecture.md)
> - Khảo sát công cụ hiện có và tự động hóa: [../khao-sat/tu-dong-hoa-dau-tu.md](../khao-sat/tu-dong-hoa-dau-tu.md)
> - Khảo sát sstock: [../khao-sat/sstock.md](../khao-sat/sstock.md)

## 0. Tóm tắt

- **MVP trong một câu:** khi một mã VN30 công bố BCTC quý 3/2026, trong vòng 30 phút có một **thẻ KQKD đã kiểm chứng**.
  - Thẻ có các con số chính so với cùng kỳ và % kế hoạch năm.
  - Thẻ có **cờ cảnh báo khi con số tăng trưởng dễ gây hiểu nhầm**.
  - Mỗi số bấm vào là thấy trang PDF gốc.
  - Người theo dõi mã đó nhận **một email**.
- **Người dùng:** người dùng nội bộ và 5–10 người được mời. Sản phẩm phát hành dưới dạng cá nhân, chỉ vào được bằng lời mời, miễn phí, ghi rõ là thử nghiệm trong khuôn khổ đồ án.
- **Vì sao làm cái này trước:** nó đúng câu hỏi người đọc BCTC hỏi đầu tiên (mục 1), là phần các sản phẩm hiện có làm chưa tốt (mục 1.3), và dùng hết những gì đã xây (thu thập, đọc, kiểm chứng).
- **Mốc:**
  - bộ canh chạy trước 14/10;
  - thẻ và cờ xong 19/10;
  - web có người dùng trước đỉnh 30/10;
  - đo và phỏng vấn tới 08/11.

## 1. Người dùng cần gì

### 1.1 Người dùng chính

Nhà đầu tư cá nhân **tự ra quyết định**, thiên về phân tích cơ bản, đang có danh mục khoảng 5–15 mã, không có thời gian đọc BCTC.

**Không phục vụ trong MVP:**

| Nhóm | Lý do |
|---|---|
| Người tìm "mã hot" và tín hiệu | Rủi ro pháp lý; họ không cần số đã kiểm chứng |
| Người lướt sóng trong ngày | Cần dữ liệu khác hẳn |
| Tổ chức | Đã có FiinPro, Bloomberg |

### 1.2 Việc họ cần làm khi BCTC ra

Theo cách báo chí và CTCK trình bày KQKD, cộng với các bài tư vấn đọc KQKD, người đọc hỏi theo thứ tự:

1. **Lãi bao nhiêu, so với cùng kỳ ra sao, lũy kế đã được bao nhiêu % kế hoạch năm?**
   - Tin nhanh của báo chí luôn dùng bộ chỉ số LNST (hoặc LNTT) quý, % so với cùng kỳ và lũy kế.
   - % kế hoạch năm thường chỉ có trong ghi chú của CTCK (ví dụ VNM lũy kế 6 tháng 2026 đạt 57,4% kế hoạch năm, VCB hơn 63%).
2. **Con số đó có thật không, có "lãi ảo" không?** Các bài tư vấn khuyên "đừng chỉ nhìn vào con số tăng trưởng" và hỏi lợi nhuận có đến từ hoạt động cốt lõi không. Ví dụ thực tế:

   | Trường hợp | Ví dụ |
   |---|---|
   | Lãi nhờ chuyển nhượng | HPG quý 1/2026: khoảng 3.800 tỷ trong LNST 9.056 tỷ |
   | Lãi nhờ hoàn nhập dự phòng | GAS quý 2/2025: 1.814 tỷ |
   | Lãi nhờ thôi hợp nhất | KDH quý 2/2026; FPT quý 2/2026, xem khảo sát sstock |
   | Chuyển từ lỗ sang lãi | VIC quý 2/2026: từ lỗ 941 tỷ sang lãi 10.003 tỷ |
   | Lãi nhưng dòng tiền âm | HUT quý 2/2026 |

3. **Vì sao?** Khi LNST biến động từ 10% trở lên hoặc đổi dấu, doanh nghiệp bắt buộc phải gửi công văn giải trình.
   - Có công văn định lượng rõ (ví dụ PGV quý 1/2025: lợi nhuận gộp tăng 277 tỷ do sản lượng điện cao hơn 183,89 triệu kWh).
   - Nhiều công văn chỉ nêu chung chung.
   - Chưa có bằng chứng người dùng có đọc công văn hay không.

### 1.3 Sản phẩm hiện có làm chưa tốt ở đâu

| Vấn đề | Bằng chứng |
|---|---|
| Lỗ thu hẹp hiện như tăng trưởng | Bài tự động của DNSE: APG quý 2/2026 "lợi nhuận đạt âm 3,17 tỷ đồng, tăng trưởng 53,6%"; sstock: NTL "+91,3%" khi vẫn lỗ |
| Tin nhanh có số sai | 24HMoney 23/10/2023: VPB "giảm mạnh nhất" nhưng số ghi "từ 1.397 tỷ còn 3.117 tỷ"; HND "lãi tăng 381%" trong khi thực tế khoảng +38% |
| Không gắn cờ chất lượng lợi nhuận | sstock, CafeF, 24HMoney đều chỉ hiện số; xem khảo sát sstock |
| Không có nguồn tới trang | Không sản phẩm nào đã xem cho bấm từ con số về trang PDF |

### 1.4 Những gì **không** đưa vào và vì sao

| Không làm | Lý do |
|---|---|
| Nhận định "giá đã phản ánh", "nên mua/bán" | Phản ứng giá ở Việt Nam chậm và không đều (nghiên cứu PEAD ở Việt Nam, 2024); đây cũng là ranh giới pháp lý |
| "Vượt/trượt kỳ vọng" kiểu Simply Wall St | Việt Nam không có nguồn dự báo đồng thuận công khai; dùng % kế hoạch ĐHCĐ thay thế |
| Thông báo đẩy cho mọi biến động | Thí nghiệm của FCA (Anh, 2024) cho thấy thông báo đẩy làm tăng giao dịch và giao dịch rủi ro; chỉ gửi **một email cho mỗi BCTC** của mã đang theo dõi |
| Số "điều chỉnh" hay ước tính | Chỉ dùng số in trên BCTC |

### 1.5 Giả định chưa kiểm chứng

Kiểm chứng bằng phỏng vấn 5 người trước 26/10; kịch bản ở [user-research.md mục 7](user-research.md#7-kịch-bản-phỏng-vấn-người-dùng-1520-phút-làm-với-510-người), thêm các câu dưới đây.

| Giả định | Câu hỏi thêm vào phỏng vấn | Nếu sai thì |
|---|---|---|
| Người dùng bị con số tăng trưởng đánh lừa và muốn được cảnh báo | "Lần gần nhất bạn mua/bán vì một con số tăng trưởng, sau đó thấy không như nghĩ?" | Giảm ưu tiên cờ, tập trung vào tốc độ và độ chính xác |
| Người dùng muốn biết nguồn tới từng trang | "Bạn có từng kiểm tra lại số trên báo với BCTC gốc không?" | Giữ nguồn nhưng không đặt ở vị trí nổi bật |
| Email đủ nhanh và không bị bỏ qua | "Bạn nhận tin về mã đang giữ qua kênh nào?" | Thêm Zalo Bot sau mùa quý 3 |
| % kế hoạch năm quan trọng | "Bạn có theo dõi kế hoạch ĐHCĐ không?" | Bỏ khỏi thẻ |

## 2. Phạm vi MVP

### 2.1 Thẻ KQKD (cho mỗi mã, mỗi quý)

| Thành phần | Nội dung | Ghi chú |
|---|---|---|
| Đầu thẻ | Mã, tên, kỳ, hợp nhất hay riêng, đã soát xét hay chưa, **giờ Vietstock đăng**, giờ hệ thống xử lý xong | BCTC quý thường chưa soát xét: ghi rõ |
| Số chính, DN thường | Doanh thu thuần, lợi nhuận gộp, LNST của cổ đông công ty mẹ; quý này, cùng kỳ, % so với cùng kỳ; lũy kế và % so với cùng kỳ | |
| Số chính, ngân hàng | Thu nhập lãi thuần, tổng thu nhập hoạt động, chi phí dự phòng, LNTT, LNST của cổ đông ngân hàng | |
| % kế hoạch năm | Lũy kế chia kế hoạch ĐHCĐ 2026, có link nguồn kế hoạch | Kế hoạch nhập tay cho 30 mã |
| Cờ | Mục 2.2 | Mỗi cờ có một câu giải thích và dòng nguồn |
| Lý do theo doanh nghiệp | Tóm tắt công văn giải trình **nếu công văn có số liệu**, gắn nhãn "theo giải trình của doanh nghiệp", kèm trang | Nên có; cắt đầu tiên nếu trễ |
| Nguồn | Mỗi số mở được ảnh trang PDF gốc | Bắt buộc |
| Trạng thái | "Đã kiểm chứng (N/N ràng buộc kế toán đạt)" hoặc "Đã duyệt tay" | |

**Quy tắc hiển thị tăng trưởng:**

- Kỳ này hoặc cùng kỳ bị lỗ thì **không in %**, mà viết bằng chữ: "lỗ thu hẹp từ X còn Y", "chuyển từ lỗ X sang lãi Y", "lỗ tăng", "chuyển từ lãi sang lỗ".
- Mọi % đều kèm số tuyệt đối.

### 2.2 Cờ cảnh báo v1

Cờ là **thông tin để người đọc xem kỹ hơn**, không phải nhận định tốt hay xấu. Ngưỡng ban đầu dưới đây sẽ chỉnh sau khi chạy trên dữ liệu thật.

| Cờ | Điều kiện (tính bằng code) | Áp dụng | Ví dụ thực tế |
|---|---|---|---|
| Đổi dấu hoặc lỗ thu hẹp | LNST công ty mẹ kỳ này hoặc cùng kỳ ≤ 0 | Mọi mẫu | VIC Q2/2026, NTL Q4/2025 |
| Tăng trưởng do nền thấp | Tăng > 100% **và** LNST cùng kỳ < 1/3 trung bình 4 quý trước đó (nếu có lịch sử) | Mọi mẫu | KSF, MSR Q2/2026 (sstock) |
| Lợi nhuận phần lớn ngoài hoạt động chính | Lợi nhuận cốt lõi = LN gộp − CP bán hàng − CP quản lý. Cờ khi phần còn lại của LNTT > 50% LNTT, hoặc cốt lõi ≤ 0 < LNTT | DN thường | HPG Q1/2026, HBC Q2/2023 |
| Hoàn nhập dự phòng lớn | DN thường: dòng "các khoản dự phòng" trên LCTT âm và lớn hơn 20% LNTT lũy kế. Ngân hàng: chi phí dự phòng đổi dấu (hoàn nhập) hoặc giảm > 50% so với cùng kỳ trong khi LNTT tăng | DN thường, ngân hàng | GAS Q2/2025 |
| Thay đổi phạm vi hợp nhất | LCTT có dòng tiền của công ty con khi mất hoặc giành quyền kiểm soát; hoặc lãi từ công ty liên doanh, liên kết tăng hơn 3 lần | DN thường | FPT Q2/2026 (dòng 26b, −713 tỷ), KDH Q2/2026 |
| LNST dương, dòng tiền KD lũy kế âm | LNST lũy kế > 0 và lưu chuyển tiền thuần từ HĐKD lũy kế < 0 | DN thường (không áp dụng cho ngân hàng) | HUT Q2/2026 |

Nên có thêm nếu kịp: cờ lãi/lỗ tỷ giá lớn; chuỗi 4–8 quý để người đọc tự thấy nền thấp hoặc đỉnh chu kỳ.

### 2.3 Web, chỉ vào được bằng lời mời

| Trang | Nội dung |
|---|---|
| `/mua-bctc/q3-2026` | 30 mã VN30: đã hoặc chưa công bố, giờ công bố, LNST và % so với cùng kỳ (theo quy tắc hiển thị ở 2.1), các cờ. Lọc theo ngành, theo danh sách theo dõi |
| `/ma/{mã}` | Thẻ KQKD quý mới nhất, các quý trước, nguồn |
| `/theo-doi` | Thêm hoặc bớt mã trong danh sách theo dõi |
| `/duyet` (chỉ người dùng nội bộ) | Hàng BCTC chưa đạt kiểm chứng: con số đặt cạnh ảnh trang PDF; duyệt, sửa hoặc từ chối |

- **Đăng nhập** bằng link gửi qua email; chỉ email trong danh sách mời mới vào được.
- **Thiết kế** ưu tiên điện thoại.
- Có nhãn "Nội dung do AI hỗ trợ trích xuất, đã kiểm chứng bằng ràng buộc kế toán" và trang phương pháp ngắn.

### 2.4 Email

- Một email cho mỗi BCTC của mã đang theo dõi, gửi ngay khi thẻ được xuất bản (đã kiểm chứng hoặc đã duyệt tay).
- Nội dung: dòng tiêu đề có LNST và cờ, ba số chính, các cờ, link tới thẻ.
- Không gửi thông báo theo giá.

### 2.5 Người duyệt (HITL ở khâu xuất bản)

- **Đạt mọi ràng buộc bắt buộc:** tự xuất bản.
- **Không đạt:**
  - hệ thống đã tự đọc lại ô và chép lại theo trang (thang leo thang trong pipeline) mà vẫn lệch thì vào hàng duyệt;
  - người dùng nội bộ xem số cạnh ảnh PDF, sửa nếu cần, rồi xuất bản;
  - mọi sửa tay được ghi lại (ai, khi nào, giá trị cũ và mới) và trở thành dữ liệu vàng cho đánh giá.
- **Mục tiêu:** không có con số sai nào được xuất bản.

### 2.6 Ngoài phạm vi MVP

- Danh mục và giá vốn.
- Đặt lệnh, và hỗ trợ ra quyết định có người duyệt (phần mở rộng ĐATN, cho người dùng nội bộ, sau mùa quý 3).
- Chatbot.
- VN100.
- Công ty chứng khoán và bảo hiểm (SSI, TCX hiện "chưa kiểm chứng").
- Sàng lọc tăng trưởng và backtest.
- SEO, Next.js, MCP, Zalo.

## 3. Hiện trạng kỹ thuật (11/10/2026)

| Thành phần | Trạng thái |
|---|---|
| Thu thập (Vietstock), CSDL, tải file | Xong; quét VN30 hết khoảng 1 phút |
| Bộ canh tự động | Chạy liên tục từ 11/10, mỗi 15 phút; email cho người vận hành chờ cấu hình SMTP |
| Đọc và kiểm chứng BCTC: TT200, TT99, ngân hàng | Xong bản đầu. Toàn bộ BCTC hợp nhất quý 2/2026 của VN30 thuộc các mẫu đã hỗ trợ: **26/28 tự đạt mọi ràng buộc bắt buộc** (14/15 DN thường, 12/13 ngân hàng); khoảng 0,09 USD mỗi BCTC |
| Hai BCTC chưa đạt | VIC: BCTC không in cột mã số dù là DN thường, cần ánh xạ theo tên chỉ tiêu như ngân hàng. SHB: mô hình đọc nhầm tên một dòng KQKD, nên số bị gán sai chỉ tiêu; vào hàng duyệt tay |
| Đọc và kiểm chứng BCTC: công ty chứng khoán | Chưa có ràng buộc (SSI, TCX) |
| Bộ duyệt tay (đo độ chính xác theo ô) | Mẫu đã có, **chưa điền** |
| Ánh xạ chỉ tiêu chuẩn TT200/TT99/ngân hàng | Bản đầu |
| Bộ tính chỉ số, cờ, web, email cho người dùng | Chưa có |

## 4. Lịch làm việc

| Thời gian | Việc | Người làm | Xong khi |
|---|---|---|---|
| **11–13/10** | Chạy nốt BCTC quý 2 VN30, đo tỷ lệ tự kiểm chứng, sửa lỗi gặp phải. Chạy bộ canh liên tục. Cấu hình email cho người vận hành | Kỹ thuật | Bộ canh chạy trước khi BCTC quý 3 đầu tiên xuất hiện |
| | Thuê VPS, mua tên miền (nếu muốn), tạo mật khẩu ứng dụng Gmail | Bạn | |
| **14–19/10** | Bộ tính chỉ số, quy tắc hiển thị tăng trưởng, 6 cờ v1, API trả về thẻ. Ánh xạ theo tên chỉ tiêu cho DN thường không in mã số (VIC). Chạy bù quý 1/2026 và quý 4/2025 (chỉ BCTC hợp nhất) | Kỹ thuật | Thẻ đúng cho 30 mã quý 2 |
| | Nhập kế hoạch ĐHCĐ 2026 cho 30 mã. Duyệt tay bộ rút gọn: các ô hiện trên thẻ, khoảng 25 ô × 5 BCTC | Bạn (~3 giờ) | Có số độ chính xác theo ô đầu tiên |
| **20–26/10** | Web: bảng mùa, trang mã, theo dõi, hàng duyệt, đăng nhập bằng email. Triển khai lên VPS | Kỹ thuật | Chạy trên điện thoại, có HTTPS |
| | Mời 5–10 người; phỏng vấn 5 người theo mục 1.5 | Bạn | |
| **27/10–08/11** | Email cho danh sách theo dõi; tóm tắt giải trình (nếu kịp); vận hành qua đỉnh 30/10; đo các chỉ số mục 5; chạy "ChatGPT test" với 20 câu hỏi về KQKD quý 3 | Cả hai | Có số liệu cho báo cáo tuần |
| 09/11–06/12 | Theo kế hoạch học kỳ: agent phân tích và báo cáo so sánh, VN100; cờ v2 và sàng lọc tăng trưởng v1 | | |

**Nếu trễ thì cắt theo thứ tự:**

1. tóm tắt giải trình;
2. cờ hoàn nhập dự phòng và cờ thay đổi phạm vi hợp nhất;
3. email (người dùng tự vào web).

**Không được cắt:** thẻ, quy tắc hiển thị tăng trưởng, cờ đổi dấu, cờ nền thấp, cờ lợi nhuận ngoài hoạt động chính, nguồn tới từng trang, hàng duyệt.

## 5. Đo thành công

| Nhóm | Chỉ số | Mục tiêu mùa quý 3 |
|---|---|---|
| Dữ liệu | % BCTC VN30 tự đạt kiểm chứng | ≥ 90% |
| | Độ chính xác theo ô trên bộ duyệt tay (các ô hiện trên thẻ) | ≥ 99% |
| | Số sai được xuất bản | 0 |
| Tốc độ | Từ lúc Vietstock đăng tới lúc thẻ xuất bản, trung vị | < 30 phút |
| Người dùng | Người được mời quay lại ≥ 3 lần trong mùa | ≥ 5/10 |
| | Câu trả lời phỏng vấn mục 1.5 | Ghi nguyên văn |
| Chi phí | USD cho mỗi BCTC | ≤ 0,1 |

Số người dùng ở mức này chỉ để học hỏi, không đủ để kết luận về nhu cầu.

## 6. Vận hành và chi phí

| Hạng mục | Lựa chọn | Chi phí ước tính |
|---|---|---|
| Máy chủ | VPS 2 vCPU, 2–4 GB RAM, Ubuntu; Docker Compose gồm CSDL, web (FastAPI), bộ canh; Caddy cấp HTTPS | ~5 USD/tháng |
| Tên miền | Tùy chọn (có thể dùng tên miền miễn phí lúc đầu) | ~10 USD/năm |
| Email | Gmail SMTP với mật khẩu ứng dụng (đủ cho vài chục người dùng) | 0 |
| Mô hình | OpenAI `gpt-5.4-mini` (đang dùng thử; chọn chính thức sau khi có bộ duyệt tay) | Quý 3 VN30 ~3 USD; chạy bù 3 quý ~9 USD |
| Sao lưu | `pg_dump` hằng ngày lên Google Drive | 0 |

## 7. Rủi ro

| Rủi ro | Cách giảm |
|---|---|
| Vietstock chặn hoặc đăng chậm hơn HOSE | Quét nhẹ (1 giây giữa các request); ghi thêm giờ HOSE cho vài mã để so; chuẩn bị nguồn dự phòng (CafeF, HOSE) |
| Độ chính xác chưa đo | Duyệt tay bộ rút gọn trước 19/10; hàng duyệt chặn số sai |
| Biến thể tên chỉ tiêu ngân hàng mới | Sửa mẫu tên rồi kiểm tra lại từ kết quả đã lưu, không tốn tiền gọi mô hình |
| Một người làm, giữa học kỳ | Thứ tự cắt ở mục 4 |
| Cờ bị hiểu là khuyến nghị | Câu chữ trung lập ("cần xem thêm"), trang phương pháp, không xếp hạng "nên mua" |
| Phát hành cá nhân vẫn chịu luật về tư vấn đầu tư | Chỉ cung cấp số liệu đã công bố và cảnh báo trung lập; không khuyến nghị; chỉ người được mời |

## 8. Nguồn (bằng chứng ở mục 1)

- 24HMoney, "Những lưu ý quan trọng trong mùa báo cáo" (21/07/2025): https://24hmoney.vn/news/nhung-luu-y-quan-trong-trong-mua-bao-cao-c30a2613001.html
- 24HMoney, cập nhật KQKD quý 3/2023 (23/10/2023): https://24hmoney.vn/news/cap-nhat-kqkd-quy-3-2023-chieu-23-10-doanh-nghiep-nhiet-dien-bat-ngo-bao-lai-tang-381-c2a2076472.html
- DNSE, bài tự động APG quý 2/2026: https://www.dnse.com.vn/senses/tin-tuc/bctc-quy-22026-apg-khoi-sac-quy-2-loi-nhuat-dat-am-317-ty-dong-tang-truong-536-so-voi-cung-ky-35248898
- VietTimes, lãi đột biến (14/08/2025): https://viettimes.vn/loat-doanh-nghiep-bao-lai-dot-bien-but-toan-hay-thuc-luc-post188369.html
- VietnamFinance, HPG quý 1/2026: https://vietnamfinance.vn/diem-danh-cac-doanh-nghiep-lai-dot-bien-nho-dut-ao-ban-con-d144722.html
- MekongAsean, GAS quý 2/2025: https://mekongasean.vn/nho-hoan-nhap-du-phong-pv-gas-bao-lai-sau-thue-quy-22025-cao-nhat-13-quy-44507.html
- MekongAsean, lợi nhuận quý 2/2026 theo ngành (KDH, VIC): https://mekongasean.vn/nganh-nao-tang-truong-loi-nhuan-manh-nhat-quy-22026-58274.html
- Báo Đấu thầu, HBC quý 2/2023: https://baodauthau.vn/can-canh-doanh-nghiep-lai-lon-tu-thu-nhap-bat-thuong-post141969.html
- Công văn giải trình PGV quý 1/2025: https://static2.vietstock.vn/data/HOSE/2025/BCTC/VN/QUY%201/PGV_Giaitrinh_KQKD_Q1_2025.pdf
- Ho, Nguyen & Tran (2024), PEAD ở Việt Nam: https://ideas.repec.org/a/eee/riibaf/v70y2024ipbs0275531924001454.html
- Hirshleifer, Lim & Teoh (2009), nhiều công bố cùng lúc: https://www.nber.org/papers/w11683
- FCA (2024), thí nghiệm thông báo đẩy trong ứng dụng giao dịch: https://www.fca.org.uk/publications/research-notes/research-note-digital-engagement-practices-trading-apps-experiment

Lưu ý: không đọc trực tiếp được diễn đàn F319 và các nhóm Facebook, nên bằng chứng về hành vi trên diễn đàn là gián tiếp qua báo chí. Đây là lý do cần phỏng vấn ở mục 1.5.
