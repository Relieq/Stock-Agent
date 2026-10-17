# Kế hoạch MVP: mùa BCTC quý 3/2026

> Lập ngày 11/10/2026. Thầy hướng dẫn chưa phản hồi về hướng ĐATN, nên từ nay dự án tự chủ trương; tài liệu này là mốc để bám theo và để báo cáo lại.
> Tài liệu liên quan:
> - Nhu cầu người dùng nói chung: [user-research.md](user-research.md)
> - Kiến trúc: [architecture.md](architecture.md)
> - Khảo sát công cụ hiện có và tự động hóa: [../khao-sat/tu-dong-hoa-dau-tu.md](../khao-sat/tu-dong-hoa-dau-tu.md)
> - Khảo sát sstock: [../khao-sat/sstock.md](../khao-sat/sstock.md)

## 0. Tóm tắt

- **MVP trong một câu:** khi một mã VN30 công bố BCTC quý 3/2026, trong vòng 30 phút có một **thẻ KQKD đã kiểm chứng**.
  - Thẻ có các con số chính so với cùng kỳ (% kế hoạch năm hoãn từ 12/10, xem mục 2.1).
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
| % kế hoạch năm | **Hoãn (12/10/2026).** Không làm thẻ chính xác hơn, lại phải nhập tay 30 nghị quyết mỗi năm. Code đã có (`agm_plans`, `python -m services.metrics plans`); chỉ bật lại nếu phỏng vấn cho thấy người dùng cần | |
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
| Số liệu bị sửa giữa các BCTC (thêm 11/10) | Doanh thu, LNTT hoặc LNST khác giữa hai BCTC của cùng công ty (quý 2 với bán niên đã soát xét, quý này với lũy kế quý trước), chênh từ 0,5% và từ 1 tỷ; số đã được đọc lại để loại lỗi đọc | Mọi mẫu | VPL: LNST 6 tháng giảm 40 tỷ sau soát xét; VIC: LNTT 6 tháng tăng 694 tỷ |

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

### 2.6 BCTC ngoài danh sách theo dõi (thêm vào MVP ngày 11/10)

BCTC là dữ liệu công khai nên chỉ có **một kho chung**: mỗi BCTC chỉ đọc một lần, mọi người dùng sau dùng lại kết quả.

| Trường hợp | Cách xử lý |
|---|---|
| Người dùng hỏi một mã chưa theo dõi | Tìm BCTC trên Vietstock, đọc và kiểm chứng như VN30 (khoảng 0,1 USD, vài phút), lưu vào kho chung |
| Người dùng tải file lên | Người dùng khai mã và kỳ. Tính mã băm SHA-256 của file: trùng file đã đọc thì trả kết quả ngay. Chưa có thì đọc 2 trang đầu (ảnh nhỏ, khoảng 0,002 USD) để kiểm tra file đúng là BCTC của mã và kỳ đã khai, sai thì từ chối. Sau đó tìm bản chính thức trên Vietstock để đọc; không tìm được thì vẫn đọc file tải lên nhưng chỉ người đó xem, ghi rõ "chưa đối chiếu với nguồn chính thức" |
| Giới hạn chi phí | Mỗi người 3 yêu cầu BCTC mới mỗi ngày, trong đó tối đa 1 file tải lên; trần chi phí gọi mô hình cho các yêu cầu này 5 USD/tháng, vượt thì xếp hàng chờ tháng sau |

### 2.7 Ngoài phạm vi MVP

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
| | Duyệt tay bộ rút gọn: các ô hiện trên thẻ, khoảng 25 ô × 5 BCTC | Bạn (~3 giờ) | Có số độ chính xác theo ô đầu tiên |
| **20–26/10** | Web: bảng mùa, trang mã, theo dõi, hàng duyệt, đăng nhập bằng email. ~~Triển khai lên VPS~~ (12/10: phát triển tiếp trên máy, chỉ triển khai khi sản phẩm hoàn thiện; BCTC quý 3 vẫn được canh/đọc trên máy hoặc chạy bù sau) | Kỹ thuật | Chạy trên điện thoại, có HTTPS |
| | Mời 5–10 người; phỏng vấn 5 người theo mục 1.5 | Bạn | |
| **27/10–08/11** | Email cho danh sách theo dõi; tóm tắt giải trình (nếu kịp); vận hành qua đỉnh 30/10; đo các chỉ số mục 5; chạy "ChatGPT test" với 20 câu hỏi về KQKD quý 3 | Cả hai | Có số liệu cho báo cáo tuần |
| 09/11–29/11 | Theo kế hoạch học kỳ (sửa 14/10: Project III kết thúc 31/12): phát hiện bất thường trong KQKD (cờ v2), agent tìm nguyên nhân trong thuyết minh và công văn giải trình (bản đầu), VN100 | | |
| 30/11–20/12 | Đánh giá độ chính xác trên bộ dữ liệu vàng, so với hệ thống khóa trước; triển khai lên VPS cho người dùng thử | | |
| 21/12–31/12 | Hoàn thiện báo cáo final, slide, video demo | | Nộp Project III |

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

## 6. Vận hành và chi phí (cập nhật 12/10/2026)

### 6.1 Hạ tầng

| Hạng mục | Lựa chọn | Chi phí ước tính |
|---|---|---|
| Máy chủ | VPS ở Việt Nam, ≥ 3 vCPU, 4–8 GB RAM, ổ ≥ 40 GB (chứa PDF), Ubuntu 24.04, ảo hóa KVM (để chạy Docker); Docker Compose gồm CSDL, web (FastAPI), bộ canh; Caddy cấp HTTPS cho `soi.rediov.com`. **Hoãn thuê tới khi sản phẩm hoàn thiện** (quyết định 12/10). Ứng viên đã so (giá 12 tháng, chưa VAT): InterData Inter Platinum 2 (5 vCPU / 8 GB, ~2,67 triệu/năm, gói khuyến mãi), LANIT VPS giá rẻ gói 2 (3 vCPU / 3,5 GB, 169k/tháng), VinaHost Cheap-SSD3 (3 vCPU / 3 GB, 225k/tháng). Trước khi trả tiền hỏi: giá đã gồm VAT chưa, giá gia hạn, băng thông quốc tế (gửi ảnh sang OpenAI), có KVM không | ~7–9 USD/tháng |
| Tên miền | `rediov.com` (đã mua trên Namecheap) | ~10 USD/năm |
| Email | Gmail SMTP với mật khẩu ứng dụng (đủ cho vài chục người dùng) | 0 |
| Mô hình đọc ảnh | OpenAI `gpt-5.4-mini`, mức suy luận `low` (thử `none` rẻ hơn ~8% nhưng sai nhiều hơn) | ~0,1 USD mỗi BCTC |
| Sao lưu | `pg_dump` hằng ngày lên Google Drive | 0 |

Vì sao vẫn cần API khi đã có VPS: VPS là máy tính thường, không có GPU. Nó làm mọi việc chạy bằng code (canh, tải, lưu,
kiểm tra cộng tổng, tính thẻ và cờ, web, email). Chỉ hai bước cần mô hình nhìn ảnh BCTC scan: tìm trang chứa bảng và chép
số. Thuê máy có GPU đắt hơn nhiều lần so với trả theo lượt khi mỗi quý chỉ đọc vài chục đến vài trăm BCTC.

Code chạy trong Docker cả khi phát triển trên máy (từ 12/10): Smart App Control của Windows chặn thư viện kết nối
PostgreSQL, và đây cũng là cách chạy trên VPS.

**Đo thử mô hình đọc tại chỗ so với gọi API (14/10/2026).** Thử PaddleOCR-VL-1.6 (0,9 tỷ tham số, Apache 2.0, nhóm điểm
cao nhất OmniDocBench) trên 3 trang BCTC:

| | Gọi API (gpt-5.4-mini) | PaddleOCR-VL, GPU laptop RTX 5050 | PaddleOCR-VL, CPU |
|---|---|---|---|
| Thời gian mỗi BCTC | khoảng 1 phút (trung vị 57 giây, 30 BCTC) | khoảng 4 phút (khoảng 25 giây/trang) | laptop i5-13450HX 4 luồng khoảng 100 giây/trang; VPS ước 25–35 phút/BCTC |
| Bộ nhớ | không đáng kể | khoảng 2 GB VRAM | khoảng 5–6 GB RAM, VPS phải lên khoảng 16 GB |
| Đọc số | scan mờ VHM: khoảng 91% | scan rõ VCB: 100%; scan mờ VHM: 78%, hay gộp dòng, tên dòng sai dấu | như GPU |
| Chi phí VN30 / VN100 mỗi năm | khoảng 21 / 70 USD | (máy cá nhân, không chạy liên tục được) | nâng VPS thêm vài chục đến hơn 100 USD/năm |

Kết luận: giữ gọi API, giữ VPS gói nhỏ. Chạy bằng CPU trên VPS vừa đắt hơn vừa không kịp mùa cao điểm (VN30 ngày hạn
chót khoảng 15 BCTC: 6–8 giờ thay vì khoảng 15 phút; VN100 hơn một ngày), lại đọc kém hơn ở bản scan mờ nên tăng đọc lại
và duyệt tay. Chỉ xem lại khi đọc toàn thị trường (khoảng 10.000 BCTC/năm, API khoảng 1.100 USD/năm): khi đó thuê GPU
theo giờ (RTX 4090 khoảng 0,34 USD/giờ) mới rẻ hơn, sau khi đo độ chính xác trên mẫu rộng. Lưu ý khi chạy PaddleOCR-VL
bằng transformers: phải bật `use_cache=True` (cấu hình gốc tắt), nếu không chậm khoảng 35 lần.

**Đo cách chuẩn bị ảnh cho bước đọc lại (14/10/2026).** Phát hiện: code không gửi tham số `detail`, nên gpt-5.4-mini dùng
mức `high`, thu ảnh về cạnh dài tối đa 2048 điểm ảnh và 2.500 ô 32×32. Ảnh "đọc lại ở độ phân giải cao" (cạnh dài 3000)
và "chép lại trang" (2600) thực tế chỉ còn khoảng 1340×1908, đúng bằng ảnh lần chép đầu. Thử trên 86 ô đã biết là đọc
sai và 86 ô đối chứng (ô đúng, lấy ngẫu nhiên trên cùng trang), 30 trang của 16 BCTC; mỗi trang một lần gọi, ô sai và ô
đối chứng trộn lẫn, không đưa số mong đợi:

| Cách | Ô sai đọc ra đúng | Ô đối chứng vẫn đúng | Chi phí |
|---|---|---|---|
| V0: như cũ (cạnh dài 3000, API tự thu nhỏ) | 39/86 (45%) | 71/86 (83%) | 0,13 USD |
| V1: V0 + `detail: original` | 49/86 (57%) | 55/86 (64%) | 0,24 USD |
| V2: vẽ đúng độ phân giải scan gốc, phóng một lần bằng Lanczos tới 288 dpi (tối đa gấp 3 ảnh gốc), `original` | 63/86 (73%) | 75/86 (87%) | 0,24 USD |
| V3: V2 + cân bằng tương phản theo vùng (CLAHE) + làm nét | 59/86 (69%) | 72/86 (84%) | 0,24 USD |

- V2 so với V0, so từng ô: 28 ô sai được đọc đúng thêm, 4 ô ngược lại (kiểm định dấu, p < 0,0001); ô đối chứng 9 tốt
  lên, 5 kém đi (không khác biệt có ý nghĩa).
- V1 làm hỏng ô đúng (22 kém đi, 6 tốt lên, p = 0,004): MuPDF phóng ảnh scan 72 dpi kiểu nhân bản điểm ảnh, chữ số răng
  cưa; trước đây API thu nhỏ nên vô tình làm mịn lại. Điều quyết định là phóng đúng cách một lần từ ảnh gốc.
- V3 không hơn V2 (chênh lệch không có ý nghĩa), bỏ. Không thử chuyển trắng đen và tăng độ phân giải bằng GAN vì tài liệu
  cho thấy rủi ro: chuyển trắng đen có thể làm kém đi trên scan chất lượng thấp, GAN có thể vẽ thêm nét giả (3 thành 8).
- Lợi ích dồn vào scan ≤ 100 dpi (ô sai đọc đúng 25/68 lên 49/68); scan nét hơn không đổi (14/18).
- Áp dụng: mọi bước đọc lại, đọc theo dải, chép lại trang dùng V2; lần chép đầu dùng V2 cho trang scan ≤ 100 dpi. Mỗi
  lần gọi tốn khoảng gấp đôi token (bước đọc lại chỉ chiếm khoảng 3% chi phí mỗi BCTC); chép đầu một trang 72 dpi tốn thêm
  khoảng 80%. Mùa quý 3 đo lại tỷ lệ đúng ngay lần đầu và chi phí cho các file mờ.
- Mỗi cách chỉ chạy một lần, kết quả từng trang dao động nhiều; kết luận V2 hơn V0 chắc chắn, chênh lệch V2–V3 thì không.

**So OpenAI với Claude ở bước đọc lại ô (17/10/2026).** Có 100 USD tín dụng Claude API. Cùng 27 trang, 71 ô đã biết
là đọc sai và 71 ô đối chứng của thí nghiệm ảnh nét (bỏ 3 trang lộn ngược); cùng ảnh V2, cùng câu lệnh và schema viết cho
OpenAI (không chỉnh cho Claude), mức suy nghĩ thấp ở cả hai; Claude giới hạn cạnh dài 2576 điểm ảnh, 4784 ô 28×28 nên ảnh
được thu nhỏ trước bằng Lanczos (khoảng 197 dpi so với 216–288 dpi của OpenAI); không bật chuyển mô hình khi bị từ chối.
Tiêu chí chốt trước khi chạy: Claude chỉ "đạt" nếu đọc đúng ô sai không ít hơn OpenAI và không hỏng thêm quá 2 ô đúng.

| Mô hình | Ô sai đọc ra đúng | Ô đối chứng vẫn đúng | Chi phí 27 trang |
|---|---|---|---|
| OpenAI gpt-5.4-mini (V2, chạy 14/10) | 57/71 (80%) | 67/71 (94%) | khoảng 0,21 USD |
| Claude Haiku 5.5 (2 lượt, kết quả giống hệt) | 66/71 (93%) | 71/71 (100%) | 0,019 USD |
| Claude Sonnet 5.5 | 66/71 (93%) | 71/71 (100%) | 0,36 USD |

So từng ô (142 ô): Claude đúng mà OpenAI sai 18, ngược lại 5 (p = 0,011), như nhau ở Haiku và Sonnet. Câu lệnh không chứa
số đáp án hay số sai cũ (đã kiểm). Chỗ Claude kém: 4 ô dòng "Lợi nhuận đã thực hiện" của TCX quý 1/2026 (trang có hai
dòng trùng tên; Haiku lấy số dòng kia, Sonnet trả rỗng, OpenAI đúng). Phép thử chỉ đo bước đọc lại (khoảng 3% chi phí);
bước chép đầu đo riêng bên dưới trước khi quyết định đổi mô hình.

**So OpenAI với Claude Haiku 5.5 ở bước chép đầu (17/10/2026).** 5 BCTC đã kiểm chứng: FPT quý 2/2026 (scan rõ), GVR
bán niên 2026 (72 dpi), TCX quý 2/2026 (công ty chứng khoán), VCB quý 2/2026 (ngân hàng), VHM quý 4/2025 (67 dpi, KQKD
trang ngang). Mỗi bên chép trọn BCĐKT, KQKD, LCTT như lần chép đầu của quy trình (mọi trang của một báo cáo trong một
lần gọi, cùng câu lệnh và schema, cùng ảnh của quy trình; Claude thu nhỏ trước theo giới hạn của nó), OpenAI chạy lại
cùng đợt. Chấm: đưa bản chép qua đúng phần chuẩn hóa, gán mã, kiểm tra của Soi rồi so từng ô với số đã kiểm chứng.

| BCTC | OpenAI: ô đúng | Claude Haiku 5.5: ô đúng | OpenAI: ràng buộc đạt / lệch | Haiku: đạt / lệch |
|---|---|---|---|---|
| FPT quý 2/2026 | 319/319 | 319/319 | 85 / 0 | 85 / 0 |
| GVR bán niên 2026 | 280/291 | 288/291 | 64 / 9 | 75 / 2 |
| TCX quý 2/2026 | 436/442 | 438/442 | 45 / 1 | 42 / 4 |
| VCB quý 2/2026 | 269/269 | 269/269 | 72 / 0 | 72 / 0 |
| VHM quý 4/2025 | 202/298 | 295/298 | 52 / 14 | 90 / 4 |
| **Tổng** | **1.506/1.619 (93,0%)** | **1.609/1.619 (99,4%)** | 318 / 24 | 364 / 10 |
| Chi phí 5 BCTC | 0,363 USD | 0,067 USD | | |
| Thời gian mỗi BCTC | khoảng 35 giây | khoảng 60 giây | | |

- VHM: OpenAI bỏ trống cả cột mã số của KQKD (chép số thứ tự nhưng không chép mã), nên 78 ô không gán được dòng; Haiku
  chép đủ. GVR: OpenAI sai 7 ô, thiếu 4; Haiku sai 1, thiếu 2. TCX: cả hai cùng thiếu một dòng KQKD (4 ô); Haiku lệch
  thêm 3 ràng buộc vì dòng đó, OpenAI sai thêm 2 chữ số.
- Haiku tốn nhiều token ra hơn (chế độ suy nghĩ luôn bật) nhưng vẫn rẻ hơn khoảng 5 lần; chậm hơn khoảng 1,7 lần.
- Giới hạn: 5 BCTC, mỗi bên một lượt.

**Trọn quy trình với Haiku và bước định vị trang (17/10/2026).** Chạy trọn quy trình bằng Haiku trên 5 BCTC trên (không
ghi CSDL): GVR, TCX, VCB đạt kiểm chứng; FPT chờ duyệt vì Haiku gán nhầm loại trang (trang 6 thuộc BCĐKT thành KQKD,
trang 7 là KQKD thành "thư"), OpenAI định vị đúng FPT từ đầu; VHM quý 4/2025 chờ duyệt (2 chỗ lệch do chính BCTC). Đo
riêng bước định vị trang trên 31 BCTC quý 2/2026 (đáp án là trang và góc xoay đã kiểm chứng):

| Cách | Đúng trang | Đủ trang (có thể thừa) | Đúng góc xoay | Chi phí |
|---|---|---|---|---|
| OpenAI gpt-5.4-mini, ảnh 900 | 28/31 | 29/31 | 31/31 | 0,60 USD |
| Claude Haiku 5.5, ảnh 900 | 29/31 | 30/31 | 27/31 | 0,09 USD |
| Claude Haiku 5.5, ảnh 1.400 | 25/31 | 26/31 | 26/31 | 0,19 USD |

Haiku xoay sai trang ngang ở MWG, TCX, VIC, VPL (trả 270, 0 hoặc 180 thay vì 90): cả báo cáo sẽ bị chép trên ảnh xoay
sai. Kết quả của Haiku ở bước này còn dao động (FPT lần này đúng). Ảnh to hơn không giúp. Kết luận: chọn nhà cung cấp
theo bước, OpenAI định vị trang, Haiku chép và đọc lại; ước tính khoảng 0,035–0,04 USD mỗi BCTC (hiện khoảng 0,11).
Đã làm: `LLM_STEP_PROVIDERS` / trang Chi phí ("Bước định vị trang: luôn dùng ...").

**Bậc chép lại cả báo cáo (đo 14/10/2026 từ nhật ký 120 BCTC).** 46 báo cáo phải chép lại, giữ bản mới 16 (cả 16 nay đạt
mọi ràng buộc bắt buộc, 4 nhờ xoay 180 độ); 30 lần không giúp gì nhưng vẫn tốn tiền (bậc này khoảng 0,033 USD mỗi BCTC).
Việc cho mùa quý 3: ghi lại đặc điểm của các lần không được giữ (số ràng buộc lệch, lệch ở một cột hay mọi cột, bước định vị
ô sai có đề xuất không) để đặt điều kiện bỏ qua bậc này khi lỗi chỉ là nhầm vài chữ số.
- Phát hiện khi xem ảnh: 3 trang (VHM quý 4/2025 trang 15, 16; VHM quý 1/2026 trang 87) bị lưu góc xoay 90 thay vì 270,
  nên mọi cách đều vẽ lộn ngược (VHM quý 4/2025: cả KQKD đã được chép trên ảnh lộn ngược, đó là nguyên nhân "cả cột hỏng").
  Đã sửa góc xoay (cả trang 17 của VHM quý 4/2025). Bỏ 3 trang này: V0 38/71 ô sai đúng (54%), ô đối chứng 64/71; V2
  57/71 (80%), 67/71; V2 so với V0: 23 tốt lên, 4 kém đi (p < 0,001); scan ≤ 100 dpi 24/53 lên 43/53.
- Kiểm lại trong quy trình thật (định vị ô sai → đọc lại → chỉ nhận khi khớp), trả các ô đã biết về số sai cũ, 4 BCTC
  mờ (GVR bán niên, VHM quý 1/2026, HDB, LPB), 51 ô: cách cũ sửa đúng 11, cách mới 20; không ô nào bị nhận nhầm;
  chi phí cách mới 0,12 USD, cách cũ 0,11 USD. (VHM quý 4/2025 không tính vì trang lộn ngược ở cả hai cách.)

### 6.2 Ngân sách đến 4/2027

Tiền gọi mô hình tăng theo **số BCTC phải đọc**, không theo số người dùng (mỗi BCTC đọc một lần, phục vụ mọi người).
Đến 11/10/2026 đã tiêu khoảng 10 USD theo các bản ghi còn lưu, phần lớn là chi phí phát triển (đọc lại cả loạt khi sửa
lỗi, thí nghiệm); số thật xem ở trang Usage của OpenAI.

| Khoản | Cách tính | Dự kiến | Trần |
|---|---|---:|---:|
| VPS | 5 → 10 USD/tháng | 50 | 60 |
| Tên miền | Đã mua | 10 | 10 |
| Mùa quý 3/2026 (VN30) | ~40 BCTC | 4 | 6 |
| Mở rộng VN100: 3 quý gần nhất của 70 mã mới | ~210 BCTC; cột "cùng kỳ" cho thêm 3 quý năm trước | 21 | 25 |
| Mùa quý 4/2026, BCTC năm 2026, quý 1/2027 (VN100) | ~300 BCTC | 30 | 40 |
| Đọc BCTC theo yêu cầu người dùng | Trần 5 USD/tháng | 15 | 35 |
| Agent viết báo cáo, bản tin sáng (mô hình chỉ viết lời) | Vài nghìn lượt × ~0,005 USD | 15 | 30 |
| Radar sự kiện (văn bản công bố) | | 10 | 20 |
| Phát triển, thí nghiệm | ~5 USD/tháng | 30 | 35 |
| **Tổng** | | **~185 USD** | **~260 USD** |

Nếu bảo vệ muộn (đến 7/2027): thêm khoảng 80 USD. Đọc toàn thị trường thêm khoảng 160 USD mỗi quý, nên chỉ đọc khi có
người yêu cầu (có trần) cho tới khi tìm được cách đọc rẻ hơn (mô hình chạy trên máy, chỉ gửi trang cần thiết).

### 6.3 Quy tắc chi tiêu

1. Giới hạn trên tài khoản OpenAI: 15 USD/tháng trong mùa BCTC, 10 USD/tháng ngoài mùa.
2. Trần trong code cho yêu cầu của người dùng: 5 USD/tháng (`LLM_MONTHLY_BUDGET_USD`).
3. Khi sửa lỗi chỉ thử trên 3–5 BCTC đại diện; sửa luật kiểm tra thì dùng `recheck` (không gọi mô hình).
4. Lần chạy nào ước tính trên 1 USD thì báo trước và chờ đồng ý; sau mỗi đợt báo chi phí (`python -m services.extraction cost`).
5. Bộ canh chỉ tự đọc BCTC của năm đang canh; dữ liệu cũ chạy bù có kiểm soát. Tài khoản hết tiền thì bộ canh dừng lượt
   đọc và giữ BCTC ở trạng thái chờ, không đánh dấu lỗi.

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
