# Kiến thức nền về thị trường chứng khoán Việt Nam (để xây sản phẩm)

> Tài liệu này dành cho người làm sản phẩm, không phải dân tài chính. Nó chỉ gồm những gì cần biết để xây đúng dữ liệu, danh mục và phân tích.
> Quy chế thay đổi theo thời gian, đặc biệt sau khi HOSE chuyển sang hệ thống giao dịch mới năm 2025. Những chỗ ghi "(kiểm tra lại)" cần đối chiếu với quy chế hiện hành trước khi viết code.

## 1. Cơ chế giao dịch: ảnh hưởng tới dữ liệu giá và backtest

| Khái niệm | Nội dung | Ảnh hưởng tới sản phẩm |
|---|---|---|
| Ba sàn | HOSE (~405 mã, chiếm phần lớn vốn hóa), HNX (~300), UPCoM (~825) | Mỗi sàn có biên độ và quy chế riêng |
| Phiên giao dịch | HOSE: ATO 9:00–9:15; khớp lệnh liên tục 9:15–11:30 và 13:00–14:30; ATC 14:30–14:45; thỏa thuận đến 15:00. Từ 5/5/2025 HOSE chạy hệ thống KRX: lệnh ATO/ATC không còn được ưu tiên hơn các lệnh đặt trước ở giá trần/sàn | Tin công bố trong giờ và ngoài giờ tác động khác nhau, nên phải lưu **giờ công bố** chính xác |
| Biên độ giá | HOSE ±7%, HNX ±10%, UPCoM ±15% so với giá tham chiếu. Ngày giao dịch đầu tiên có biên độ rộng hơn | Tin lớn có thể làm giá "chạm trần/sàn" nhiều phiên liền, nên phản ứng giá kéo dài chứ không xảy ra trong 1 phiên |
| Thanh toán T+2 | Cổ phiếu mua ngày T về tài khoản chiều T+2 mới bán được (thường gọi là "T+2.5") | Không thể mua hôm nay bán ngay hôm sau. Backtest phải tôn trọng điều này |
| Lô giao dịch | 100 cổ phiếu/lô trên HOSE. Lô lẻ (1–99) giao dịch riêng; từ khi có hệ thống KRX, lô lẻ khớp theo các phiên đấu giá 15 phút suốt ngày (kiểm tra lại) | Số lượng trong danh mục có thể lẻ do chia cổ tức |
| Bán khống | Đến 7/2026 chưa được bán khống cổ phiếu. Cho vay chứng khoán, bán khống có kiểm soát và giao dịch trong ngày (T+0) nằm trong lộ trình 2026–2028. Muốn đặt cược giá giảm thì dùng hợp đồng tương lai VN30F hoặc chứng quyền | Chiến lược "short" trên cổ phiếu cơ sở là không thực tế |
| Margin (ký quỹ) | CTCK cho vay mua cổ phiếu, lãi khoảng 10–14%/năm. Khi giá giảm mạnh sẽ bị "call margin", rồi "bán giải chấp" | Rủi ro dây chuyền khi thị trường giảm. Phần quản trị rủi ro cần tính cả margin |
| Room ngoại | Giới hạn sở hữu của nhà đầu tư nước ngoài (nhiều ngân hàng 30%, đa số DN 49%) | Mã hết room có hành vi giá riêng |
| Chỉ số | VN-Index (toàn HOSE), VN30 (30 mã lớn), HNX-Index, UPCoM-Index | Dùng làm chuẩn so sánh hiệu suất danh mục |

## 2. Sự kiện doanh nghiệp: phần khó nhất của việc quản lý danh mục

| Sự kiện | Chuyện gì xảy ra | Tác động tới giá vốn và lãi/lỗ |
|---|---|---|
| **Cổ tức tiền mặt** | Nhận tiền theo số cổ phiếu nắm giữ, bị khấu trừ thuế TNCN 5% | **Nhiều CTCK (TCBS, SSI, VNDIRECT) trừ cổ tức vào "giá vốn"**, nên lãi/lỗ trên app đã ngầm gồm cổ tức. "Giá vốn" trên app không phải số tiền bạn đã bỏ ra |
| **Cổ tức bằng cổ phiếu / cổ phiếu thưởng** | Nhận thêm cổ phiếu theo tỷ lệ, ví dụ 100:20 | Số lượng tăng nên **giá vốn trên mỗi cổ phiếu giảm**. Thuế 5% thường tính khi bán (kiểm tra lại) |
| **Quyền mua cổ phiếu phát hành thêm** | Được mua thêm với giá ưu đãi. Có thể bỏ quyền hoặc chuyển nhượng quyền | Nếu thực hiện quyền thì giá vốn bình quân thay đổi |
| **Ngày GDKHQ / ngày ĐKCC** | Mua **từ** ngày giao dịch không hưởng quyền (GDKHQ) thì không được hưởng quyền. Giá tham chiếu hôm đó được điều chỉnh | Nếu không điều chỉnh giá lịch sử, biểu đồ và backtest sẽ có những cú "rơi giả" |
| **Tách/gộp cổ phiếu, hoán đổi sáp nhập** | Hiếm, nhưng có | Phải có xử lý riêng |

> **Công thức điều chỉnh giá vốn các CTCK hay dùng:** `P' = (P + Pa·a − C) / (1 + a + b)`
> - `P`: giá vốn cũ; `Pa`: giá mua cổ phiếu phát hành thêm; `a`: tỷ lệ quyền mua; `b`: tỷ lệ cổ phiếu thưởng hoặc cổ tức bằng cổ phiếu; `C`: cổ tức tiền mặt trên mỗi cổ phiếu.
> - Việc điều chỉnh thường hiện lên vài ngày làm việc sau ngày chốt quyền.

> **Vì sao đây là cơ hội:** nhà đầu tư có tài khoản ở nhiều CTCK, và mỗi CTCK hiển thị giá vốn một kiểu. Hệ thống đã sẵn radar đọc công bố cổ tức và quyền mua, nên có thể **tự động** điều chỉnh giá vốn cho người dùng.

## 3. Phí và thuế: tính "lãi thật"

- **Thuế khi bán:** 0,1% trên **giá trị bán**, kể cả khi bán lỗ. Luật Thuế TNCN mới (109/2025, hiệu lực 1/7/2026) giữ nguyên mức này.
- **Thuế cổ tức tiền mặt:** 5%, được khấu trừ trước khi tiền về tài khoản.
- **Phí giao dịch:** phí trả cho Sở GDCK khoảng 0,03%; phí môi giới tùy CTCK, từ 0% (DNSE, TCBS) đến khoảng 0,15–0,3%. Có thể kèm phí lưu ký nhỏ.
- **Lãi margin:** thường khoảng 13–14%/năm (năm 2026); có chương trình ưu đãi thấp hơn.
- **Cổ tức bằng cổ phiếu:** thuế 5% thường tính khi bán. Năm 2025 từng có đề xuất thu ngay khi nhận; cần kiểm tra quy định cuối cùng.
- **Lãi margin** (nếu có vay).
- **Công thức:** lãi thật = (giá bán − giá mua) × số lượng + cổ tức đã nhận − phí − thuế − lãi vay.

## 4. Báo cáo tài chính: những gì chuyên viên phân tích AI cần hiểu

| Báo cáo | Trả lời câu hỏi | Chỉ tiêu người dùng hay hỏi |
|---|---|---|
| **Kết quả kinh doanh** | Kỳ này lãi hay lỗ, bao nhiêu? | Doanh thu thuần, lợi nhuận gộp, **LNST của cổ đông công ty mẹ** (con số báo chí hay dùng), EPS |
| **Bảng cân đối kế toán** (theo TT99 gọi là "Báo cáo tình hình tài chính") | Công ty có gì, nợ ai? | Tổng tài sản, nợ vay, vốn chủ sở hữu, hàng tồn kho, phải thu, người mua trả tiền trước (đặc biệt với BĐS) |
| **Lưu chuyển tiền tệ** | Tiền thật vào/ra bao nhiêu? | Dòng tiền từ hoạt động kinh doanh. Nếu lãi mà dòng tiền âm kéo dài thì đó là dấu hiệu cần soi |
| **Thuyết minh** | Chi tiết từng khoản | Nợ xấu (ngân hàng), chi tiết vay, giao dịch với bên liên quan |

- **Các kỳ báo cáo:** quý (tự lập), bán niên (được soát xét), năm (được kiểm toán). Hợp nhất (cả nhóm công ty) khác với riêng lẻ (chỉ công ty mẹ).
- **Các chỉ số cơ bản:** tăng trưởng so với cùng kỳ (YoY), biên lợi nhuận, ROE, ROA, nợ/vốn chủ, P/E, P/B.
- **Ngân hàng khác hẳn DN thường:** thu nhập lãi thuần, NIM, nợ xấu, chi phí dự phòng, CASA, CIR.

## 5. Dòng thông tin trên thị trường

- **Công bố thông tin chính thức** qua Sở GDCK và hệ thống IDS của UBCKNN:
  - BCTC và công văn giải trình.
  - Nghị quyết ĐHCĐ/HĐQT.
  - **Giao dịch của người nội bộ**: đăng ký trước ít nhất 3 ngày làm việc, báo cáo kết quả sau đó.
  - Thay đổi cổ đông lớn, cổ tức, phát hành thêm…
- **Tin tức:** báo tài chính (CafeF, Vietstock, VnEconomy…), báo cáo phân tích của CTCK.
- **Mạng xã hội:** group Facebook/Zalo, diễn đàn F319, KOL. Nhiều tin đồn và "phím hàng". UBCKNN đã nhiều lần cảnh báo.
- **Dòng tiền:** khối ngoại mua/bán ròng, tự doanh CTCK. Số liệu được công bố hằng ngày và nhà đầu tư Việt theo dõi rất sát.

## 6. Phân tích: ba trường phái

| Trường phái | Nhìn vào đâu | Vai trò trong "đội ngũ AI" |
|---|---|---|
| Phân tích cơ bản | BCTC, ngành, định giá | Chuyên viên phân tích BCTC (đề tài gốc) |
| Phân tích kỹ thuật | Giá, khối lượng, biểu đồ | Không phải trọng tâm. Các app môi giới đã làm rất nhiều |
| Định lượng (quant) | Dữ liệu và thống kê, kiểm định trên lịch sử | Nhà nghiên cứu định lượng: thống kê sự kiện, kiểm tra quy tắc (giai đoạn sau) |

## 7. Ranh giới pháp lý cần thuộc lòng

- **Được làm:** cung cấp thông tin và số liệu đã công bố; phân tích, thống kê; công cụ để người dùng tự ghi chép và theo dõi danh mục của chính họ; cảnh báo theo quy tắc do người dùng tự đặt; giáo dục.
- **Không được làm nếu không có giấy phép:**
  - Tư vấn đầu tư chứng khoán, tức khuyến nghị mua/bán/nắm giữ hay đưa giá mục tiêu.
  - Quản lý danh mục đầu tư cho người khác, tức nhận ủy thác tiền hoặc tài sản.
  - Tự đặt lệnh thay người dùng.
- **Dữ liệu danh mục là dữ liệu tài chính cá nhân.** Phải xin đồng ý, bảo vệ và cho phép xóa, theo Luật Bảo vệ dữ liệu cá nhân 2025.
- **Nội dung do AI tạo phải được gắn nhãn** (Luật Trí tuệ nhân tạo, hiệu lực 1/3/2026).
- **Giao dịch tự động (robot/API) của cá nhân đang là vùng xám:**
  - Tháng 9/2023, UBCKNN yêu cầu CTCK dừng đặt lệnh tự động bằng "robot", vì thông tư hiện hành chưa cho phép.
  - Năm 2026 có dự thảo thông tư về giao dịch điện tử (quy định API) và dự thảo nghị định sandbox cho phép AI đặt lệnh theo quy tắc nhà đầu tư tự đặt. Sandbox giới hạn số người tham gia và phải đi qua CTCK đủ điều kiện.
  - → **Soi không tự đặt lệnh.** Chỉ làm giao dịch giấy (paper trading) và phân tích, cho tới khi có khung pháp lý rõ ràng.

## 8. Lộ trình tự học gợi ý (2–4 tuần, song song với code)

1. **Tuần 1:** đọc hiểu một BCTC quý thật của một DN thường (ví dụ ngành bán lẻ) và một ngân hàng. Tự tính tăng trưởng YoY và biên lợi nhuận bằng tay.
2. **Tuần 2:** mở một tài khoản chứng khoán (nếu chưa có). Quan sát giá tham chiếu, trần/sàn, T+2 và ngày GDKHQ trên một mã sắp chia cổ tức.
3. **Tuần 3:** theo dõi một mùa BCTC. Đọc cách báo chí viết về KQKD, xem giá phản ứng thế nào. Ghi lại 10 quan sát.
4. **Tuần 4:** ghi chép một danh mục giả lập (paper trading) bằng Google Sheets. Tự làm sẽ thấy ngay những chỗ đau mà sản phẩm cần giải quyết.

> Mẹo: trong lúc học, mỗi khi thấy "cái này mất công quá", hãy ghi lại. Đó chính là danh sách tính năng.
