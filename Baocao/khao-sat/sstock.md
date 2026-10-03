# Khảo sát sstock.vn

> Trải nghiệm ngày 28/09/2026 theo gợi ý của thầy hướng dẫn, bằng tài khoản miễn phí (vai trò "User"). Dữ liệu dùng để thử bộ lọc là của ngày 25/09/2026, phiên gần nhất có dữ liệu.
> Ảnh chụp màn hình (31 ảnh) lưu trên [Google Drive của dự án](https://drive.google.com/drive/folders/1EhRh39TGHEqmDqDVlqXjQnkIAy3GCSt2?usp=sharing), thư mục `screenshots`. Tên ảnh ghi ở cuối mỗi mục.
> Ghi chú chỉ phản ánh những gì quan sát được tại thời điểm trải nghiệm.

## Rút ra cho đề tài

- **Nên học theo:**
  - dữ liệu BCTC nhiều kỳ, có mẫu riêng cho ngân hàng;
  - công bố công thức biểu đồ theo mã chỉ tiêu VAS;
  - bộ lọc dựng sẵn theo đặc thù ngành;
  - ghi rõ nguồn dữ liệu và công ty kiểm toán.
- **Chưa phát hiện bất thường.** Các trường hợp sau đều chưa được gắn cờ hay giải thích:
  - tăng trưởng do nền thấp (KSF, MSR);
  - lỗ thu hẹp hiển thị như tăng trưởng (NTL);
  - lợi nhuận chủ yếu từ hoạt động tài chính (NTL);
  - thay đổi phạm vi hợp nhất (FPT).

  → Khoảng trống cho hướng *phát hiện và giải thích bất thường trong kết quả kinh doanh*.
- **Chưa có sàng lọc theo phương pháp tăng trưởng chuẩn.** Chưa giải thích vì sao mã lọt lọc, chưa có backtest. Mã đang lỗ vẫn lọt bộ lọc tăng trưởng (DCL). → Khoảng trống cho hướng *sàng lọc tăng trưởng có giải thích và có kiểm chứng*.
- **Dữ liệu chỉ có số riêng từng quý:**
  - không có cột cùng kỳ, cột lũy kế;
  - thuyết minh chỉ nằm trong PDF;
  - ngày trong kho tài liệu là ngày tải lên, không phải ngày công bố.

  → Củng cố định hướng của Project 3: trích xuất đủ các cột, lưu cả thuyết minh, ghi nhận thời điểm công bố.
- **AI mới dùng để tóm tắt tin tức,** và trích nguồn chưa bấm được. → Trích dẫn trong sản phẩm phải bấm được và kiểm lại được.

## 1. Bản đồ chức năng

```
sstock.vn
├── Bảng điện: bảng giá theo VN30 và ~40 ngành, kèm cột SM; Top cổ phiếu; Diễn biến thị trường;
│   Bản đồ nhiệt; Định giá thị trường; Danh mục của tôi
├── Kênh tài sản: các kênh tài sản; tác động tới chứng khoán; vĩ mô Việt Nam
├── Thị trường: Bản đồ sức mạnh ngành; Thống kê; Định giá; Kết quả kinh doanh toàn thị trường
├── Ngành: Tổng quan (BCTC gộp ngành); Vị thế cổ phiếu; Xếp hạng cổ phiếu; Tác động ngành;
│   Định giá ngành; Mô hình kinh doanh (PDF)
├── Cổ phiếu
│   ├── Đầu trang: chỉ số tóm tắt, xếp hạng tài chính và kinh doanh, nguồn dữ liệu (WiData),
│   │   công ty kiểm toán
│   ├── Thông tin doanh nghiệp: giá, tin tức, sự kiện, hồ sơ
│   ├── Phân tích cơ bản: Bức tranh doanh nghiệp; Động lực tăng trưởng; Định giá (kèm báo cáo
│   │   của CTCK); Báo cáo tài chính; Tài liệu gốc
│   └── Phân tích kỹ thuật
├── Dòng tiền: Dòng tiền mạnh (danh sách "Top"); Bộ lọc (theo sức mạnh); Bộ lọc cơ bản (7 phương án)
├── Tin tức: lọc theo ngành; tóm tắt bằng AI
└── Đào tạo: khóa học (trả phí); hướng dẫn sử dụng; cộng đồng Discord; "Thực Chiến" (sắp ra mắt)
```

- Không có mục riêng cho AI hay chatbot, backtest, hoặc bảng giá dịch vụ.
- Mọi chức năng phân tích đã thử đều dùng được với tài khoản miễn phí. Phần trả phí là các khóa học.
- **SM** (sức mạnh) thang 0–99, là thứ hạng phần trăm so với các cổ phiếu còn lại: SM = 85 nghĩa là mạnh hơn 85% số cổ phiếu, tương tự chỉ số RS Rating của IBD.

## 2. Chi tiết từng chức năng

### 2.1 Bảng điện theo nhóm ngành
- **Làm gì:** bảng giá trong phiên, chia theo VN30 và ~40 ngành tự định nghĩa. Mỗi mã có cột SM; mỗi ngành có sức mạnh 5 phiên gần nhất.
- **Điểm hay:** gắn sức mạnh tương đối ngay vào bảng giá; phân ngành chi tiết hơn chuẩn ICB cấp 1.
- **Chưa có:** chỉ số cơ bản (tăng trưởng, P/E) trên bảng giá.
- **Ảnh:** `01-bang-dien.jpg`

### 2.2 Dòng tiền mạnh (danh sách "Top")
- **Làm gì:** danh sách mã đang "vào Top" theo hệ thống của sstock (39 mã ngày 28/09), kèm ngày vào Top, số ngày ở trong Top, giá lúc vào và giá hiện tại.
- **Điểm hay:** theo dõi hiệu quả sau khi mã vào Top, giống một bảng kiểm chứng nhỏ.
- **Chưa có / cần lưu ý:**
  - Chưa công bố tiêu chí vào Top. Chưa có thống kê tổng hợp: tỷ lệ thắng, lợi nhuận trung bình, so sánh với VN-Index.
  - Chỉ hiện các mã còn trong Top; mã đã rời Top không còn hiện. Vì vậy hiệu quả nhìn thấy bị **thiên lệch sống sót** (survivorship bias).
  - HTM hiển thị giá hiện tại 0,00 và −100%.
- **Liên quan đề tài:** sàng lọc tăng trưởng (động lượng giá, gần chữ L trong CANSLIM); cách kiểm chứng một bộ lọc.
- **Ảnh:** `02-dong-tien-manh.jpg`

### 2.3 Bộ lọc theo sức mạnh
- **Làm gì:** lọc theo 3 tiêu chí: SM ngắn hạn, SM trung hạn, khối lượng trung bình 20 phiên. Chọn được ngày trong quá khứ và xuất được dữ liệu.
- **Điểm hay:** vì chọn được ngày quá khứ, về nguyên tắc có thể dựng lại danh sách lọc tại một thời điểm (point-in-time) để tự backtest.
- **Chưa có / cần lưu ý:**
  - chỉ có 3 tiêu chí;
  - cột tên "MA20" thực chất là khối lượng trung bình 20 phiên;
  - không giải thích vì sao một mã lọt lọc.
- **Liên quan đề tài:** sàng lọc tăng trưởng.
- **Ảnh:** `03-bo-loc-suc-manh-ket-qua.jpg`

### 2.4 Bộ lọc cơ bản (7 phương án dựng sẵn)
- **Làm gì:** kết hợp yếu tố cơ bản và dòng tiền. Mọi phương án đều yêu cầu vốn hóa ≥ 1.000 tỷ và khối lượng trung bình 20 phiên ≥ 400 nghìn, cộng thêm tiêu chí riêng:

  | Phương án | Ngành | Tiêu chí riêng |
  |---|---|---|
  | Tiêu chuẩn | Tất cả | LNST công ty mẹ tăng ≥ 15% so với cùng kỳ trong 1, 2 hoặc 3 quý liên tiếp; SM ngắn hạn ≥ 80; SM trung hạn ≥ 70 |
  | Mở rộng sản xuất | Phi tài chính | (TSCĐ + XDCB dở dang) tăng ≥ 20% so với cùng kỳ |
  | Đầu cơ tồn kho | Phi tài chính | Tồn kho tăng ≥ 30% so với quý trước |
  | Đại gia tiền mặt | Phi tài chính | (Tiền − Nợ vay) / Tổng tài sản ≥ 30% |
  | Bất động sản | BĐS | Tồn kho và người mua trả tiền trước cùng tăng ≥ 10% so với quý trước |
  | CK cho vay margin | Chứng khoán | Cho vay / Tổng tài sản ≥ 40%; Margin / VCSH ≥ 40% |
  | CK tự doanh | Chứng khoán | Tự doanh / Tổng tài sản ≥ 20%; Cổ phiếu / Tự doanh ≥ 30% |

  Kết quả chia 3 tab:
  - tiêu chí lọc;
  - dòng tiền kỹ thuật;
  - cơ bản doanh nghiệp: LNST 4 quý, P/E, P/B, EPS, ROA, ROE.

  Phương án Tiêu chuẩn ngày 25/09 cho ra 28 mã.
- **Điểm hay:**
  - Có bộ lọc dựng sẵn. Phương án "Tiêu chuẩn" gần với chữ C (tăng trưởng lợi nhuận quý) và chữ L (sức mạnh tương đối) trong CANSLIM.
  - Các phương án theo đặc thù ngành (BĐS, chứng khoán) là ý tưởng hay.
- **Chưa có / cần lưu ý:**
  - Chưa có bộ lọc theo các phương pháp chuẩn: CANSLIM đầy đủ, GARP/PEG, 4M, Piotroski F-score, Magic Formula. Chưa lọc được theo doanh thu, EPS năm, PEG, biên lợi nhuận.
  - Chưa giải thích vì sao mã lọt lọc, chưa có điểm tổng hợp, chưa lưu được bộ lọc tự tạo.
  - Chưa phân biệt tăng trưởng do nền thấp: MSR +29.415% và BSR +782% (quý 2/2026) đứng chung với các mã tăng trưởng bình thường.
  - DCL lọt bộ lọc tăng trưởng (+157%) dù LNST 4 quý gần nhất là −2,26 tỷ, EPS −31 đồng.
  - Khối lượng trung bình 20 phiên của cùng một mã khác nhau giữa hai tab (MSR: 2.013.985 và 3.021.600).
- **Liên quan đề tài:** sàng lọc tăng trưởng là chính; các trường hợp trên cũng là ví dụ tốt cho phát hiện bất thường.
- **Ảnh:** `04-bo-loc-co-ban-phuong-an.jpg`, `05-bo-loc-co-ban-ket-qua.jpg`, `06-bo-loc-co-ban-tab-co-ban-dn.jpg`, `07-bo-loc-co-ban-tab-dong-tien.jpg`, `08-bo-loc-co-ban-quy-lien-tiep.png`

### 2.5 Hướng dẫn sử dụng: định nghĩa "Sức mạnh"
- **Nội dung:** SM là thứ hạng phần trăm so với các cổ phiếu còn lại. Hướng dẫn gọi đây là "tiêu chí quan trọng nhất" trong phương pháp của sstock.
- **Chưa có:**
  - công thức: khung thời gian ngắn hạn, trung hạn; dựa trên giá hay khối lượng;
  - định nghĩa ngắn hạn và trung hạn đang được viết giống nhau.
- **Ảnh:** `09-huong-dan-suc-manh.jpg`

### 2.6 Trang cổ phiếu: phần đầu trang
- **Làm gì:**
  - chỉ số tóm tắt: vốn hóa, P/B, P/E, ROA/ROE, EPS;
  - **nguồn dữ liệu (WiData)** và **công ty kiểm toán** (FPT: PwC, TCB: EY, NTL: A&C);
  - xếp hạng tài chính và kinh doanh trong ngành;
  - ngân hàng có bộ chỉ số riêng (CAR, tăng trưởng tín dụng).
- **Điểm hay:** ghi rõ nguồn dữ liệu và công ty kiểm toán; có chỉ số riêng cho ngân hàng.
- **Chưa có:** cách tính xếp hạng tài chính và kinh doanh.
- **Liên quan đề tài:** sàng lọc (xếp hạng); phát hiện bất thường (công ty kiểm toán là một yếu tố rủi ro).
- **Ảnh:** `13-loi-bo-cuc-header.jpg`

### 2.7 Phân tích cơ bản: Bức tranh doanh nghiệp
- **Làm gì:** 6 biểu đồ trong 17 quý:
  - cơ cấu tài sản;
  - nguồn vốn;
  - cơ cấu lợi nhuận (kinh doanh, tài chính, khác);
  - lưu chuyển tiền tệ;
  - cơ cấu chi phí;
  - KQKD theo quý.
- **Điểm hay:**
  - **Công bố công thức.** PDF "Công thức tính biểu đồ cơ bản" ánh xạ từng thành phần tới mã chỉ tiêu VAS (ví dụ: Tiền và tiền gửi = A.I.1 + A.II.3 + B.V.5).
  - Biểu đồ được thiết kế theo mô hình ngành.
- **Chưa có:** cảnh báo hay chú thích khi số liệu thay đổi bất thường. Ví dụ FPT quý 1/2026:
  - doanh thu thuần giảm 22,3% so với cùng kỳ;
  - so với quý 4/2025:
    - tổng tài sản giảm từ 88.142 xuống 68.586 tỷ;
    - TSCĐ giảm từ 17.289 xuống 11.625 tỷ;
    - đầu tư tài chính dài hạn tăng từ 4.738 lên 10.525 tỷ;
    - chi phí bán hàng giảm từ 2.027 xuống 1.002 tỷ;
    - LNST của cổ đông không kiểm soát giảm từ 485 xuống −11 tỷ;
    - lãi từ công ty liên doanh, liên kết tăng từ 284 lên 667 tỷ;
    - biên lợi nhuận ròng tăng từ 12% lên 20%.

  Đây là dấu hiệu thường gặp khi **thôi hợp nhất một công ty con**, cần đọc thuyết minh để xác nhận. Trang chỉ vẽ số liệu, không giải thích.
- **Liên quan đề tài:** phát hiện bất thường là chính.
- **Ảnh:** `10-fpt-buc-tranh-doanh-nghiep.jpg`, `11-cong-thuc-bieu-do-pdf.jpg`, `12-fpt-co-cau-chi-phi-kqkd-quy.jpg`

### 2.8 Phân tích cơ bản: Động lực tăng trưởng
- **Làm gì:**
  - kết quả kinh doanh 4 quý gần nhất (TTM) đặt cạnh giá cổ phiếu;
  - tăng trưởng theo quý;
  - ROA/ROE;
  - biên lợi nhuận.
- **Điểm hay:** đặt lợi nhuận TTM cạnh giá để thấy độ lệch giữa định giá và lợi nhuận.
- **Chưa có:**
  - tăng trưởng kép 3–5 năm;
  - EPS theo năm;
  - đánh giá chất lượng tăng trưởng: lợi nhuận cốt lõi so với khoản bất thường, dòng tiền kinh doanh so với lợi nhuận.
- **Ảnh:** `14-fpt-dong-luc-tang-truong.jpg`

### 2.9 Phân tích cơ bản: Định giá
- **Làm gì:** P/E, P/B theo thời gian; danh sách báo cáo phân tích của các CTCK, gồm tiêu đề, khuyến nghị, giá mục tiêu, ngày.
- **Điểm hay:** tổng hợp báo cáo của các CTCK, có ghi nguồn.
- **Chưa có:** mô hình định giá riêng; tổng hợp giá mục tiêu.
- **Ảnh:** `15-fpt-dinh-gia-bao-cao-phan-tich.jpg`

### 2.10 Phân tích cơ bản: Báo cáo tài chính
- **Làm gì:**
  - 3 bảng KQKD, CĐKT, LCTT trong 17 quý (Q2/2022 đến Q2/2026), hoặc theo năm;
  - xen kẽ các dòng tăng trưởng, biên lợi nhuận, EPS;
  - đổi được đơn vị, xuất được file;
  - mẫu VAS cho doanh nghiệp thường, mẫu riêng cho ngân hàng.
- **Điểm hay:** đủ 17 quý cho cả 3 báo cáo; xuất được dữ liệu; có mẫu riêng cho ngân hàng.
- **Chưa có / cần lưu ý:**
  - Chỉ có số riêng từng quý hoặc cả năm. **Không có cột cùng kỳ, không có cột lũy kế** (6 tháng, 9 tháng); tăng trưởng chỉ là một dòng %.
  - Không có BCTC riêng của công ty mẹ dạng bảng (chỉ có PDF), không có thuyết minh. Từ con số không có liên kết về BCTC gốc.
  - Chưa gắn cờ bất thường:
    - NTL có các mức tăng trưởng LNST 26.807% và 172.883%;
    - "lỗ thu hẹp" hiển thị như tăng trưởng dương: NTL quý 4/2025 lỗ 3 tỷ so với lỗ 35 tỷ, hiện +91,3%.
  - Khi chọn đơn vị tỷ, số của doanh nghiệp nhỏ bị làm tròn đến hàng đơn vị, dễ gây hiểu nhầm. NTL quý 2/2026 hiện 5 so với 1 tỷ, trong khi tăng trưởng ghi +228%.
- **Liên quan đề tài:** phát hiện bất thường là chính; dữ liệu cho Project 3.
- **Ảnh:** `16-fpt-bctc-kqkd.jpg`, `17-fpt-bctc-can-doi.jpg`, `21-tcb-bctc-kqkd.jpg`, `22-ntl-bctc-kqkd.jpg`

### 2.11 Phân tích cơ bản: Tài liệu
- **Làm gì:** kho tài liệu gốc, lọc được theo năm và loại. Gồm BCTC hợp nhất và riêng, nghị quyết HĐQT, tài liệu ĐHĐCĐ, báo cáo quản trị…
- **Điểm hay:** có tài liệu gốc để đối chiếu số liệu và đọc thuyết minh.
- **Cần lưu ý:** ngày hiển thị là ngày tải lên hệ thống, không phải ngày công bố. Ví dụ, tài liệu ĐHĐCĐ các năm 2020–2025 đều ghi 31/07/2026. Vì vậy không dùng được để biết thông tin có từ khi nào.
- **Liên quan đề tài:** kiểm chứng; dữ liệu theo thời điểm công bố để backtest.
- **Ảnh:** `18-fpt-tai-lieu.jpg`

### 2.12 Mô hình kinh doanh
- **Làm gì:** infographic dạng PDF về chuỗi giá trị đầu vào → hoạt động → đầu ra của ngành hoặc doanh nghiệp.
- **Điểm hay:** giúp hiểu nhanh mô hình kinh doanh; có thể dùng làm ngữ cảnh cho agent.
- **Chưa có:** liên kết với số liệu.
- **Ảnh:** `19-mo-hinh-kinh-doanh-fpt.jpg`

### 2.13 Ngành: Xếp hạng cổ phiếu
- **Làm gì:** xếp hạng doanh nghiệp trong ngành (chung, tài chính, kinh doanh), kèm EPS, P/E, P/B, doanh thu, LNST, tăng trưởng. Chọn được cột hiển thị.
- **Điểm hay:** so sánh trong cùng ngành.
- **Chưa có / cần lưu ý:**
  - chưa công bố cách xếp hạng (tiêu chí, trọng số);
  - ngành ngân hàng hiển thị tổng thu nhập hoạt động (TOI) và LNST bằng 0 cho mọi ngân hàng;
  - tiêu đề ghi "Q2/26" nhưng thời điểm cập nhật là 06/06/2026.
- **Ảnh:** `20-xep-hang-nganh-ngan-hang-loi-toi.jpg`

### 2.14 Tin tức: tóm tắt bằng AI
- **Làm gì:** AI tóm tắt 20 tin mới nhất của nhóm đã chọn (VN30 hoặc một ngành) thành các chủ đề và một đoạn tổng quan, khoảng 250 từ, trong 5–10 giây. Có ghi chú "Nội dung do AI tạo, chỉ mang tính tham khảo".
- **Chất lượng:** mạch lạc, gom nhóm hợp lý. Đối chiếu thử 3 chủ đề đầu thì đều khớp đúng tin.
- **Cần lưu ý:**
  - trích nguồn chỉ là "(chủ đề N)", không bấm được, không ghi tên báo;
  - thứ tự tin đổi sau mỗi lần lọc nên khó kiểm lại.
- **Chưa có:** AI cho BCTC (đọc, giải thích, chấm điểm); chatbot hỏi đáp.
- **Liên quan đề tài:** bài học về trích dẫn: phải bấm được và kiểm lại được.
- **Ảnh:** `23-ai-tom-tat-tin-tuc.jpg`

### 2.15 Khung chat
- **Đã thử:** lúc 14:14 ngày 28/09/2026, gửi câu hỏi về cách tính chỉ số sức mạnh.
- **Kết quả:**
  - sau khoảng 40 giây không có phản hồi, không có tin chào tự động;
  - khung chat mang tên tài khoản người dùng, không phải tên bot.

  Nhiều khả năng đây là kênh hỗ trợ do người trả lời, không phải chatbot.
- **Ảnh:** `30-khung-chat.jpg`, `31-khung-chat-da-gui.png`

### 2.16 Thị trường: Bản đồ sức mạnh ngành
- **Làm gì:** heatmap sức mạnh của ~40 ngành theo từng ngày, so với VN-Index; xuất được file.
- **Điểm hay:** thấy được dòng tiền luân chuyển giữa các ngành.
- **Chưa có:** công thức.
- **Liên quan đề tài:** sàng lọc (chọn ngành dẫn dắt, gần chữ L và I trong CANSLIM).
- **Ảnh:** `24-ban-do-suc-manh-nganh.jpg`

### 2.17 Thị trường: Kết quả kinh doanh toàn thị trường
- **Làm gì:** bảng mọi mã, gồm LNST 5 quý (Q2/2025 đến Q2/2026), tăng trưởng 4 quý, P/E, P/B. Mỗi cột lọc được theo ngưỡng ≥ hoặc ≤.
- **Điểm hay:** gần nhất với cách lọc kiểu CANSLIM (chữ C): lọc được "LNST tăng ≥ X% trong cả 4 quý".
- **Chưa có / cần lưu ý:**
  - chỉ có LNST, không có doanh thu hay EPS;
  - chưa lưu được bộ lọc;
  - chưa đánh dấu tăng trưởng do nền thấp hay do thu nhập bất thường. Ví dụ: KSF +11.944% (quý 2/2026), VGI +5.631% (quý 1/2026), BSR +3.741% (quý 4/2025).
- **Liên quan đề tài:** sàng lọc tăng trưởng là chính; phát hiện bất thường.
- **Ảnh:** `25-kqkd-toan-thi-truong.jpg`, `26-kqkd-loc-theo-cot.jpg`

### 2.18 Danh mục và cảnh báo
- **Làm gì:** danh mục theo dõi (watchlist) đơn giản: thêm mã, xem giá, %, khối lượng. Chưa tạo thử.
- **Chưa có:**
  - cảnh báo (giá, KQKD, bất thường);
  - danh mục đầu tư có giá vốn và lãi/lỗ.
- **Ảnh:** `27-danh-muc.png`, `28-dong-tien-nuoc-ngoai.png`

### 2.19 Gói dịch vụ
- Không có trang bảng giá hay nâng cấp.
- Với tài khoản miễn phí, mọi chức năng phân tích đã thử đều mở: lọc, BCTC 17 quý, AI tóm tắt, xuất dữ liệu.
- Phần trả phí là khóa học (ví dụ "Phân tích đầu tư ngành Thép", 499.000đ, 8 buổi) và "Đào tạo thực chiến".
- **Ảnh:** `29-khoa-hoc-tra-phi.jpg`

### 2.20 Chưa đi sâu
- **Các mục chưa tìm hiểu kỹ:**
  - Kênh tài sản;
  - Thống kê và Định giá thị trường;
  - Tổng quan ngành, Vị thế cổ phiếu, Tác động ngành, Định giá ngành;
  - Bản đồ nhiệt, Top cổ phiếu;
  - Phân tích kỹ thuật.
- **Trải nghiệm chung:** một số trang tải chậm (bộ lọc cơ bản mất khoảng 10–15 giây). Phần đầu trang cổ phiếu có lúc hiển thị chồng chữ khi chuyển tab. Các điểm này không liên quan tới đề tài nên không đi sâu.

## 3. Tổng hợp

### 3.1 Đối chiếu với nhu cầu của đề tài

| Chức năng | sstock | Ghi chú |
|---|---|---|
| BCTC nhiều kỳ | Có | 17 quý hoặc theo năm, đủ 3 báo cáo, mẫu riêng cho ngân hàng, xuất được file |
| Cột cùng kỳ, lũy kế | Chưa có | Chỉ có dòng % so với cùng kỳ |
| Thuyết minh, BCTC riêng dạng bảng | Chưa có | Chỉ có PDF gốc |
| Ngày công bố thật của tài liệu | Chưa có | Ngày hiển thị là ngày tải lên |
| Công bố công thức | Một phần | Có cho biểu đồ; chưa có cho sức mạnh, xếp hạng, danh sách Top |
| Bộ lọc dựng sẵn | Có | 7 phương án riêng của sstock |
| Bộ lọc theo phương pháp chuẩn | Chưa có | CANSLIM, GARP, 4M, Piotroski, Magic Formula |
| Giải thích vì sao mã lọt lọc | Chưa có | Chỉ hiện bảng số |
| Phát hiện và giải thích bất thường | Chưa có | Có "xếp hạng tài chính, kinh doanh" nhưng chưa rõ cách tính |
| Backtest, thống kê hiệu quả | Chưa có | Chỉ có bảng giá lúc vào Top so với giá hiện tại |
| AI | Một phần | Chỉ tóm tắt tin tức; trích nguồn chưa bấm được |
| Watchlist | Có | Danh sách đơn giản |
| Cảnh báo | Chưa có | |

### 3.2 Năm điểm mạnh
1. **BCTC 17 quý** theo mẫu VAS, có mẫu riêng cho ngân hàng, xuất được file, kèm kho tài liệu gốc.
2. **Công bố công thức biểu đồ** (ánh xạ tới mã chỉ tiêu VAS); ghi rõ nguồn dữ liệu và công ty kiểm toán.
3. **Phương án lọc theo đặc thù ngành:**
   - BĐS: tồn kho, người mua trả tiền trước;
   - chứng khoán: margin, tự doanh;
   - "đại gia tiền mặt", "mở rộng sản xuất".
4. **Sức mạnh tương đối** cho cổ phiếu và ngành theo từng ngày, có lịch sử và chọn được ngày quá khứ.
5. **Bảng KQKD toàn thị trường** lọc được theo cột, cùng với phần tổng hợp báo cáo phân tích của các CTCK.

### 3.3 Năm khoảng trống
1. **Chưa phát hiện bất thường.** Chưa gắn cờ:
   - tăng trưởng do nền thấp (NTL +172.883%, MSR +29.415%);
   - thay đổi phạm vi hợp nhất (FPT);
   - lợi nhuận tài chính lấn át hoạt động chính (NTL quý 2/2026 có LNST 4,76 tỷ, lớn hơn cả doanh thu 4,75 tỷ);
   - lợi nhuận lệch với dòng tiền kinh doanh.
2. **Chưa có bộ lọc theo phương pháp tăng trưởng chuẩn.** Thiếu tiêu chí doanh thu, EPS năm, tăng trưởng kép, PEG, chất lượng lợi nhuận.
3. **Chưa giải thích và chưa minh bạch.** Chưa nói vì sao mã lọt lọc; chưa công bố cách tính sức mạnh, xếp hạng, tiêu chí vào Top.
4. **Chưa có backtest** hay thống kê hiệu quả cho các phương án lọc.
5. **Dữ liệu chưa nhất quán ở một số chỗ:**
   - DCL đang lỗ vẫn lọt bộ lọc tăng trưởng;
   - "lỗ thu hẹp" hiển thị như tăng trưởng dương;
   - khối lượng trung bình 20 phiên khác nhau giữa hai tab;
   - HTM có giá bằng 0;
   - xếp hạng ngành ngân hàng có doanh thu và lợi nhuận bằng 0.

### 3.4 Số liệu tham chiếu (quý 2/2026, BCTC hợp nhất, theo sstock)

| Mã | Loại | Doanh thu thuần / Thu nhập lãi thuần | LNST cổ đông công ty mẹ | Tổng tài sản |
|---|---|---|---|---|
| FPT | Doanh nghiệp thường | 13.789 tỷ (−17,1%) | 2.568 tỷ (+13,7%) | 73.734 tỷ |
| TCB | Ngân hàng | 10.763 tỷ (+17,8%) | 7.350 tỷ (+17,7%) | 1.273.077 tỷ |
| NTL | Bất động sản, vốn hóa nhỏ | 4,748 tỷ (−22,7%) | 4,764 tỷ (+228%) | 2.059,9 tỷ |

- Số % là tăng trưởng so với cùng kỳ.
- Số của NTL lấy theo đơn vị triệu đồng để không bị làm tròn.
- Bảng này sẽ dùng để đối chiếu với kết quả trích xuất của Project 3 từ BCTC gốc.

### 3.5 Câu hỏi còn bỏ ngỏ
1. Công thức chỉ số sức mạnh (khung thời gian; dựa trên giá hay khối lượng) và xếp hạng tài chính, kinh doanh (tiêu chí, trọng số) là gì?
2. Tiêu chí để một mã vào danh sách "Top" là gì? Có lưu lịch sử các mã đã rời Top không?
3. Số liệu lấy từ BCTC hợp nhất hay riêng, trước hay sau kiểm toán? Khi có BCTC điều chỉnh, số các quý cũ có được cập nhật lại không?
4. Câu hỏi gửi qua khung chat lúc 14:14 ngày 28/09 đã có người trả lời chưa?
