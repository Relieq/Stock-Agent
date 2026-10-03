# Khảo sát: công cụ tài chính, quy trình đầu tư và tự động hóa có con người duyệt (HITL)

> Tra cứu web ngày 03/10/2026, chia bốn mảng: công cụ quốc tế, hạ tầng tại Việt Nam, quy trình của một bộ phận đầu tư, và cách đặt con người vào vòng lặp.
> Mục tiêu: xác định phần nào của việc đầu tư cá nhân nên tự động hóa, phần nào phải giữ con người duyệt.
> Phạm vi: tự động hóa cho **tài khoản của chính mình**. Bán tín hiệu, copy trade hay đặt lệnh hộ người khác cần giấy phép và nằm ngoài tài liệu này (xem [mục 3.3](#33-pháp-lý)).
> Nhiều chi tiết chỉ có nguồn thứ cấp hoặc chưa mở được văn bản gốc; các điểm đó gom ở [mục 6](#6-điểm-chưa-xác-minh). Tài liệu này không phải tư vấn đầu tư hay tư vấn pháp lý.

## Rút ra

- **Chưa có bằng chứng độc lập cho thấy agent LLM tự chọn cổ phiếu và thắng thị trường.** Các bài kiểm tra ngoài mẫu (StockBench, FINSABER, Alpha Arena) cho kết quả kém hoặc không hơn mua và nắm giữ. Lợi nhuận backtest của LLM thường đến từ việc mô hình đã "nhớ" dữ liệu quá khứ. → Không giao quyền chọn mã và quyết định mua bán cho LLM.
- **Tự động hóa giúp cá nhân nhiều nhất ở kỷ luật, không phải ở việc tìm thêm cơ hội.** Nghiên cứu hành vi cho thấy cá nhân thua chủ yếu vì giao dịch quá nhiều và vì giữ mã lỗ, chốt sớm mã lãi. Lệnh thoát cam kết trước làm giảm rõ hiệu ứng này trong thí nghiệm.
- **Ngành quản lý quỹ cũng dừng ở mức "co-pilot".** Khảo sát Mercer: đa số nhà quản lý đã dùng AI cho nghiên cứu và xử lý dữ liệu, nhưng chỉ khoảng 6% để AI ra quyết định. Các quỹ lớn dùng agent để nghiên cứu và soạn thảo, còn người quản lý danh mục vẫn ký duyệt.
- **Hạ tầng tại Việt Nam đã đủ để tự động hóa cho tài khoản cá nhân.** SSI, DNSE và TCBS mở API giao dịch cho khách hàng cá nhân. Cả ba đều cần xác thực OTP đầu phiên, sau đó đặt lệnh không cần xác nhận lại trong khoảng 8 giờ. Đây là điểm duyệt tối thiểu có sẵn, nhưng chưa đủ: sau OTP không còn ai chặn từng lệnh.
- **Thị trường cơ sở không cho quay vòng trong ngày** (T+2, chưa có T+0 và bán khống). Tự động hóa cổ phiếu vì vậy là bài toán theo dõi, tái cân bằng và thoát lệnh theo quy tắc, không phải giao dịch tần suất cao.
- **Khoảng trống trùng với hướng của đề tài:**
  - dữ liệu BCTC có cấu trúc, có dẫn nguồn cho thị trường ngoài Mỹ;
  - lớp kiểm chứng số liệu trong sản phẩm cho cá nhân;
  - lớp kiểm chứng số liệu trong sản phẩm cho cá nhân;
  - nhật ký quyết định và kiểm tra kỷ luật (luận điểm, điều kiện sai, nhắc rà soát);
  - đánh giá ngoài mẫu trung thực cho chiến lược có LLM;
  - điểm duyệt của con người khi đặt lệnh: các broker nước ngoài năm 2026 đang bớt dần bước xác nhận từng lệnh.
- **Đề xuất:** tự động hóa cao ở khâu dữ liệu, sàng lọc, theo dõi và báo cáo; con người quyết định mua bán và tỷ trọng; lệnh chỉ được gửi sau khi người xác nhận, trong hạn mức cứng viết bằng code. Chi tiết ở [mục 5](#5-đề-xuất-tự-động-hóa-gì-giữ-con-người-ở-đâu).

## 1. Công cụ hiện có trên thế giới

### 1.1 Cho tổ chức

| Nhóm | Ví dụ | Làm gì |
|---|---|---|
| Terminal dữ liệu | Bloomberg, LSEG Workspace, FactSet, S&P Capital IQ, Koyfin | Dữ liệu, tin tức, phân tích. Bloomberg (ASKB, 02/2026) và LSEG đều đã mở dữ liệu cho agent qua MCP |
| Nghiên cứu, đọc tài liệu | AlphaSense, Daloopa, Quartr, Fiscal.ai, Hebbia, Rogo, Brightwave | Tìm kiếm và tóm tắt hồ sơ công bố, cập nhật mô hình tài chính từ BCTC, transcript họp nhà đầu tư |
| Trợ lý của hãng LLM | ChatGPT for Financial Services (10/09/2026) và các bản tương tự của hãng khác | Nối dữ liệu có bản quyền (FactSet, S&P, Daloopa…) vào trợ lý; nhắm tới công việc của chuyên viên phân tích |
| Danh mục, lệnh, rủi ro | BlackRock Aladdin, Charles River, SimCorp (gồm Axioma), Bloomberg AIM/PORT, MSCI Barra, Addepar | Quản lý vòng đời lệnh, kiểm tra tuân thủ trước giao dịch, mô hình rủi ro, báo cáo hiệu quả |
| Định lượng, backtest | QuantConnect (LEAN), Qlib + RD-Agent, vectorbt, backtrader, OpenBB, Numerai | Nghiên cứu tín hiệu, backtest, tối ưu danh mục |

Ba thuật ngữ hay gặp:
- **OMS** (Order Management System): quản lý vòng đời lệnh, phân bổ, kiểm tra tuân thủ trước giao dịch.
- **EMS** (Execution Management System): định tuyến và thực thi lệnh, thuật toán khớp.
- **PMS** (Portfolio Management System): vị thế, NAV, hiệu suất, kế toán danh mục.

### 1.2 Cho nhà đầu tư cá nhân

- **Sàng lọc và phân tích:** TradingView, Finviz, Simply Wall St, Seeking Alpha, Morningstar, Stock Rover.
- **Theo dõi danh mục:** Sharesight, Snowball Analytics, getquin, Empower, Ghostfolio (mã nguồn mở, tự host).
- **Robo-advisor** (Betterment, Wealthfront): khách đồng ý một lần về hồ sơ rủi ro và phân bổ mục tiêu, sau đó hệ thống tự tái cân bằng, tự tối ưu thuế, tự nạp định kỳ. Chúng **không** chọn cổ phiếu theo quan điểm.
- **Tự động hóa ở broker:**

| Broker | Tự động hóa gì | Con người ở đâu |
|---|---|---|
| Interactive Brokers | API lâu năm; năm 2026 mở kết nối MCP cho các trợ lý AI | Chưa xác minh được có cho đặt lệnh qua MCP hay chỉ đọc |
| Alpaca | API giao dịch, MCP server chính thức, đặt lệnh bằng ngôn ngữ tự nhiên | Tùy phần mềm phía người dùng; có paper trading cùng đặc tả API |
| Composer (SoFi mua 06/2026) | Chiến lược theo luật, AI soạn từ mô tả | Người duyệt chiến lược trước khi chạy tiền thật |
| M1 | Tỷ trọng mục tiêu, tự tái cân bằng | Người đặt tỷ trọng |
| eToro | Sao chép người khác hoặc agent | Chọn đối tượng để sao chép |
| Public (03/2026) | Mô tả chiến lược, xác nhận một lần, sau đó tự chạy | Chỉ duyệt lúc đầu |

### 1.3 Agent AI cho đầu tư

| Dự án | Cách làm | Ghi chú |
|---|---|---|
| TradingAgents | 4 agent phân tích (cơ bản, tâm lý, tin tức, kỹ thuật), hai bên tranh luận tăng/giảm, trader, nhóm rủi ro, quản lý danh mục | Mã nguồn mở, ghi rõ chỉ để nghiên cứu |
| ai-hedge-fund | Các agent định giá, tâm lý, cơ bản, kỹ thuật, rủi ro, danh mục | Mục đích giáo dục, không đặt lệnh thật |
| FinRobot, FinGPT, FinMem | Nền tảng agent, LLM tài chính mã nguồn mở, agent có bộ nhớ phân tầng | |
| AlphaAgents (BlackRock, 2025) | Các agent tranh luận để chọn cổ phiếu | Bài nghiên cứu |
| RD-Agent (Microsoft) | Tự đề xuất nhân tố, viết code, backtest, lặp lại | Kết quả do tác giả tự báo cáo |

Ở các quỹ, mẫu chung là agent nghiên cứu và soạn thảo, con người giữ quyền phủ quyết: Man Group đưa tín hiệu do AI đề xuất qua quy trình thẩm định của người; Magnetar (06/2026) dự định dùng agent thay nhóm phân tích nhưng người quản lý danh mục vẫn quyết định.

### 1.4 Bằng chứng về hiệu quả

| Nguồn | Kết quả |
|---|---|
| Vals Finance Agent v2 (cập nhật 01/10/2026) | 927 câu hỏi mức chuyên viên mới vào nghề; mô hình dẫn đầu đúng 65,4%; yếu nhất ở dựng mô hình tài chính (34,5%) |
| FinanceBench (2023) | GPT-4 Turbo kèm truy xuất tài liệu sai hoặc từ chối 81% câu hỏi; chỉ đạt 85% khi được đưa đúng ngữ cảnh |
| StockBench (10/2025) | Đa số agent LLM không thắng chiến lược mua và nắm giữ chia đều |
| FINSABER (05/2025) | Backtest 20 năm trên hơn 100 mã: lợi thế LLM từng công bố suy giảm mạnh |
| Profit Mirage (10/2025), Memorization Problem (04/2025) | Lợi nhuận backtest biến mất khi ra ngoài giai đoạn mô hình đã học; dặn mô hình "không dùng kiến thức tương lai" không ngăn được |
| Alpha Arena mùa 1 (cuối 2025, tiền thật, crypto) | 4/6 mô hình lỗ, giao dịch quá nhiều nên phí ăn hết lãi. Mẫu quá nhỏ để kết luận thống kê |

Kết luận: LLM đọc và tra cứu tài liệu đã khá, nhưng chưa đủ tin cậy để bỏ bước kiểm tra. Mọi backtest nằm trong giai đoạn dữ liệu huấn luyện của mô hình đều đáng ngờ.

## 2. Quy trình của một bộ phận đầu tư

Bảng dưới là quy trình **chuẩn mực** tổng hợp từ giáo trình CFA, tài liệu nhà cung cấp OMS và bài viết hành nghề, không phải quan sát tại một quỹ cụ thể.

| Bước | Ai làm | Đầu ra | Mức tự động hóa hiện nay |
|---|---|---|---|
| 1. Chính sách đầu tư (IPS) | Giám đốc đầu tư, hội đồng đầu tư | Mục tiêu, khẩu vị rủi ro, hạn mức, benchmark | Con người; hạn mức được mã hóa vào hệ thống |
| 2. Xác định nhóm mã được đầu tư | Quản lý danh mục, tuân thủ | Danh sách mã được phép | Tự động phần lớn |
| 3. Tạo ý tưởng, sàng lọc | Chuyên viên phân tích | Danh sách rút gọn, watchlist | Bán tự động; nơi AI được dùng nhiều nhất |
| 4. Nghiên cứu cơ bản | Chuyên viên phân tích theo ngành | Mô hình tài chính, định giá, báo cáo | Thu thập dữ liệu tự động một phần; giả định do người |
| 5. Tờ trình, hội đồng đầu tư | Chuyên viên trình, hội đồng quyết | Tờ trình đầu tư, biên bản | Con người (AI hỗ trợ soạn) |
| 6. Xây dựng danh mục, tỷ trọng | Quản lý danh mục | Tỷ trọng mục tiêu, lệnh đề xuất | Bán tự động, người ký |
| 7. Tuân thủ trước giao dịch | Hệ thống và bộ phận tuân thủ | Lệnh được duyệt hoặc bị gắn cờ | Tự động theo luật; ngoại lệ do người xử lý |
| 8. Thực thi | Trader | Khớp lệnh, phân tích chi phí giao dịch | Tự động cao ở thị trường phát triển |
| 9. Hậu giao dịch | Bộ phận vận hành, ngân hàng lưu ký | Đối chiếu, NAV | Tự động cao |
| 10. Theo dõi | Chuyên viên, quản lý danh mục | Ghi chú cập nhật, theo dõi luận điểm | Bán tự động |
| 11. Quản trị rủi ro | Bộ phận rủi ro độc lập | Báo cáo rủi ro, vi phạm hạn mức | Tính toán tự động, diễn giải do người |
| 12. Đo lường hiệu quả | Bộ phận đo lường hiệu quả | Báo cáo phân rã lợi nhuận | Tự động |
| 13. Báo cáo | Quản lý danh mục, quan hệ khách hàng | Báo cáo tháng, quý | Số liệu tự động, bình luận do người |
| 14. Hậu kiểm | Quản lý danh mục, giám đốc đầu tư | Bài học, sửa quy trình | Con người |

- **Phân vai:** chuyên viên phân tích đề xuất; quản lý danh mục quyết định và chịu trách nhiệm; trader thực thi; rủi ro và tuân thủ **độc lập** với bộ phận đầu tư.
- **Quỹ định lượng:** con người phán đoán khi thiết kế mô hình, không phải ở từng lệnh. Rủi ro chính là overfitting, thiên lệch sống sót, rò rỉ dữ liệu và giả định khớp lệnh phi thực tế.
- **Tại Việt Nam:**
  - VCBF công bố quy trình 6 bước: sàng lọc, nghiên cứu sâu, cơ cấu danh mục 25–50 mã, thực hiện, theo dõi, tái cơ cấu.
  - Dragon Capital và VinaCapital mô tả nghiên cứu cơ bản bởi đội phân tích nội bộ rồi trình hội đồng đầu tư.
  - Thông tư 99/2020/TT-BTC (về công ty quản lý quỹ, khác với Thông tư 99/2025 về chế độ kế toán) yêu cầu kiểm soát nội bộ, quản trị rủi ro và tách biệt nghiên cứu, thực hiện đầu tư, quản lý tài sản.
  - Công cụ quan sát được: FiinPro-X và Excel.
- **Khảo sát về AI trong quản lý tài sản:**
  - Mercer 2024: 54% đang dùng AI trong chiến lược hoặc nghiên cứu; chỉ 6% để AI ra quyết định.
  - Mercer 2026: 55% đã tích hợp AI vào ít nhất một quy trình. Lợi ích ghi nhận là hiệu suất vận hành (69%); cải thiện lợi nhuận chỉ 8%. Rào cản chính là chất lượng dữ liệu (69%).

### Quy trình tương ứng của một cá nhân

| Bước của tổ chức | Tương ứng cá nhân |
|---|---|
| Chính sách đầu tư | Bản chính sách cá nhân: mục tiêu, khẩu vị rủi ro, phân bổ, quy tắc tái cân bằng |
| Nhóm mã, sàng lọc | Tiêu chí lọc cố định và watchlist |
| Nghiên cứu, tờ trình | Checklist nghiên cứu và bản luận điểm một trang viết **trước khi mua**, kèm điều kiện làm luận điểm sai |
| Xây dựng danh mục, tuân thủ | Quy tắc tỷ trọng tối đa mỗi mã và mỗi ngành, kiểm tra trước khi đặt lệnh |
| Theo dõi | Cập nhật theo KQKD quý, cảnh báo tin tức |
| Đo lường, hậu kiểm | Nhật ký đầu tư, rà soát định kỳ so với benchmark |

Cá nhân không có bộ phận rủi ro và tuân thủ độc lập. Quy tắc viết sẵn và hạn mức bằng code đóng vai trò thay thế.

## 3. Hạ tầng tại Việt Nam

### 3.1 API giao dịch và dữ liệu

| CTCK | Cá nhân dùng được | Phạm vi | Xác thực |
|---|---|---|---|
| SSI FastConnect | Có; tài liệu v3 ghi rõ đối tượng gồm cá nhân tự động hóa chiến lược | Cơ sở và phái sinh; REST và WebSocket; SDK nhiều ngôn ngữ | Khóa ký RS256 kèm OTP; OTP có thể giữ hiệu lực 8 giờ |
| DNSE Lightspeed / OpenAPI | Có; cá nhân đăng ký online | Giao dịch, dữ liệu thị trường; cơ sở và phái sinh; có plugin AmiBroker (Ami X) | Smart OTP hoặc Email OTP, token 8 giờ |
| TCBS iFlash Open API | Có vẻ có; API key tạo trên TCInvest | Tài khoản, tiền, lệnh cổ phiếu, lệnh phái sinh, dữ liệu | API key kèm OTP, token tối đa 8 giờ |
| VPS, VNDirect, Pinetree, KIS, MBS | Không tìm thấy tài liệu API công khai cho cá nhân | | |

- **Thử nghiệm không dùng tiền thật:** SSI có ứng dụng Paper Trading (chưa rõ có API); Algotrade có nền tảng paper trading dùng giao thức FIX.
- **Dữ liệu:**
  - vnstock: bản cộng đồng chỉ cho cá nhân, học tập, nghiên cứu; giấy phép không phủ dữ liệu gốc.
  - FiinQuant: gói miễn phí 33 mã, 1 năm lịch sử; giá các gói trả phí không công khai.
  - WiGroup: khoảng 800–1.600 USD/năm.
  - Dữ liệu SSI và DNSE đi kèm tài khoản; chưa thấy điều khoản phân phối lại.
- **Cộng đồng algo:** Algotrade.vn, XNO Quant, QM Trade, AmiBroker (phổ biến nhất cho bot phái sinh). Phần lớn hoạt động algo trong nước tập trung ở hợp đồng tương lai VN30.
- **Sản phẩm tự động cho cá nhân:** Fmarket và Finhay có đầu tư định kỳ tự động; TCBS iCopy tự khớp lệnh theo người được sao chép. Không tìm thấy sản phẩm nào tự tái cân bằng danh mục cổ phiếu riêng lẻ.

### 3.2 Ràng buộc của thị trường

| Hạng mục | Hiện trạng |
|---|---|
| Thanh toán | T+2; chứng khoán về trước 13h ngày T+2, bán được phiên chiều |
| T+0, bán khống | Chưa triển khai trên thị trường cơ sở; lãnh đạo VSDC nói sớm nhất nửa cuối 2026, nhiều khả năng 2027–2028 |
| Biên độ | HOSE ±7%, HNX ±10%, UPCoM ±15% |
| Lô | Lô chẵn 100 cổ phiếu |
| Loại lệnh | HOSE: ATO, LO, MTL, ATC; HNX thêm MOK, MAK, PLO |
| Margin | Ký quỹ ban đầu tối thiểu 50%, duy trì tối thiểu 30% |
| Phí và thuế | Phí môi giới thực tế 0–0,3%; thuế bán 0,1% trên giá trị bán kể cả khi lỗ; thuế cổ tức tiền mặt 5% |

### 3.3 Pháp lý

- **Đặt lệnh tự động trên tài khoản của chính mình:** chưa rõ ràng, cần kiểm tra trước khi dùng tiền thật.
  - Lần tra cứu này không tìm thấy văn bản cấm hay văn bản quy định riêng, và các CTCK đang công khai cấp API cho cá nhân.
  - Tuy nhiên [user-research.md, mục 3](../dinh-huong/user-research.md#3-người-làm-quantalgo-8-nhu-cầu) ghi nhận năm 2023 UBCKNN từng yêu cầu CTCK dừng đặt lệnh "robot", và năm 2026 có dự thảo sandbox cho AI đặt lệnh chưa ban hành. Hai nguồn này chưa được đối chiếu với nhau.
  - Chưa đọc được điều khoản hợp đồng của CTCK nào về bot.
- **Quy định đang thay đổi:** UBCKNN đang lấy ý kiến dự thảo thông tư thay Thông tư 134/2017 (giao dịch điện tử), có nội dung về kết nối API với bên thứ ba. Chưa xác minh được đã ban hành hay chưa.
- **Vùng cần giấy phép:** quản lý tiền hoặc danh mục của người khác, tư vấn đầu tư, phát tín hiệu mua bán. UBCKNN đã nhiều lần cảnh báo các ứng dụng và nhóm khuyến nghị không phép.
- **Hệ quả cho sản phẩm Soi:** phần tự động hóa cho tài khoản riêng phải tách khỏi sản phẩm công khai. Sản phẩm công khai vẫn chỉ cung cấp thông tin, đúng ranh giới ở [vision-and-roadmap.md, mục 3.5](../dinh-huong/vision-and-roadmap.md#35-pháp-lý-cần-biết-ngay-từ-đầu).

## 4. Con người trong vòng lặp (HITL)

### 4.1 Các mức tự động hóa

- Không có chuẩn "mức tự chủ" chính thức nào dành riêng cho đầu tư.
- Khung phù hợp nhất là của Parasuraman, Sheridan và Wickens (2000): chọn mức tự động **riêng cho từng loại chức năng** (thu thập thông tin, phân tích, chọn quyết định, thực thi). Nhờ vậy có thể tự động cao ở dữ liệu và thấp ở quyết định.
- Feng và cộng sự (2025) chia 5 mức theo vai trò của người dùng: người vận hành, người cộng tác, người tư vấn, người duyệt, người quan sát. Luận điểm chính: mức tự chủ là lựa chọn thiết kế, tách khỏi năng lực của agent.
- Bốn chế độ thường gặp trong tài chính:
  - **Hỗ trợ quyết định:** máy chỉ cung cấp thông tin.
  - **Human-in-the-loop:** người duyệt từng hành động.
  - **Human-on-the-loop:** máy tự làm trong hạn mức, người giám sát và có nút dừng.
  - **Tự động trong ủy quyền:** kiểu robo-advisor.

### 4.2 Kiểm soát rủi ro lấy từ quy định về giao dịch thuật toán

Các kiểm soát dưới đây lấy từ MiFID II RTS 6 (EU), SEC Rule 15c3-5 và hướng dẫn FINRA 15-09 (Mỹ). Chúng áp cho tổ chức, nhưng dùng được làm danh sách kiểm tra cho hệ thống cá nhân.

| Kiểm soát | Mục đích |
|---|---|
| Giới hạn giá trị và khối lượng mỗi lệnh | Chặn lệnh to bất thường do lỗi của agent hoặc của người |
| Giới hạn giá so với thị trường | Chặn lệnh lệch xa giá hiện tại |
| Hạn mức vị thế nối trực tiếp với việc chặn lệnh | Hạn mức chỉ để hiển thị là vô dụng |
| Lỗ tối đa trong ngày | Dừng khi thua lỗ tích lũy |
| Giới hạn số lệnh trong một khoảng thời gian | Chặn vòng lặp gửi lệnh |
| Nút dừng khẩn cấp | Hủy mọi lệnh chờ và dừng hệ thống ngay |
| Đối soát sau giao dịch | So vị thế thực tại CTCK với sổ nội bộ |
| Quản lý thay đổi và lưu phiên bản | Tránh lỗi triển khai |
| Thử ở môi trường tách biệt, rồi vốn nhỏ | Giảm thiệt hại khi mới chạy |
| Nhật ký đầy đủ | Truy vết được mọi quyết định |
| Người vận hành không tự ghi đè được kiểm soát | Giữ kiểm soát độc lập với người ra quyết định |

Bài học Knight Capital (2012): lỗ hơn 460 triệu USD trong khoảng 45 phút vì triển khai code lỗi, trong khi hạn mức không nối với việc chặn lệnh.

### 4.3 Mẫu HITL trong hệ agent LLM

- **Cổng duyệt trước hành động không đảo ngược.** Hướng dẫn quản trị agent của OpenAI nêu đích danh giao dịch tài chính là loại cần người chủ động cho phép.
- **Tạm dừng và tiếp tục** (LangGraph `interrupt()`): agent dừng, lưu trạng thái, chờ người trả lời rồi chạy tiếp. Khi tiếp tục, node chạy lại từ đầu, nên thao tác đặt lệnh phải nằm sau điểm dừng hoặc ở node riêng và phải idempotent.
- **Leo thang theo mức rủi ro:** chỉ hỏi người ở tình huống rủi ro hoặc đã định trước.
- **Chạy bóng, paper trading, rồi triển khai theo giai đoạn với hạn mức vốn.**

### 4.4 Khi việc duyệt của con người thất bại

- **Thiên lệch tự động hóa:** người duyệt tin máy quá mức; xảy ra ở cả chuyên gia và không khắc phục được chỉ bằng huấn luyện.
- **Mỏi cảnh báo:** trong y khoa, 49–96% cảnh báo thuốc bị bỏ qua.
- **Duyệt cho có:** khi phải duyệt quá nhiều, người duyệt nhanh và kém cân nhắc.
- **Cách giảm:**
  - ít cổng duyệt nhưng mỗi cổng có trọng lượng;
  - buộc người tự ghi quyết định và lý do trước khi xem đề xuất của máy;
  - hệ thống trình bày được lập luận và nguồn;
  - hạn mức cứng bằng code thay cho việc trông vào sự chú ý của người.

### 4.5 Bằng chứng hành vi

- **Giao dịch quá nhiều:** Barber và Odean (2000), 66.465 hộ: nhóm giao dịch nhiều nhất đạt 11,4% mỗi năm trong khi thị trường đạt 17,9%.
- **Giữ mã lỗ, chốt sớm mã lãi:** Odean (1998), 10.000 tài khoản.
- **Cam kết trước có hiệu lực:** Fischbacher và cộng sự (2017, thí nghiệm): có sẵn lệnh cắt lỗ và chốt lời tự động làm giảm đáng kể hiệu ứng trên.
- **Checklist và nhật ký quyết định:** không tìm được nghiên cứu thực nghiệm chất lượng chứng minh hiệu quả; coi là thực hành hợp lý nhưng chưa có bằng chứng.

## 5. Đề xuất: tự động hóa gì, giữ con người ở đâu

Phần này là đề xuất thiết kế suy ra từ các mục trên, không phải kết luận của một nguồn nào.

### 5.1 Theo từng bước

| Bước | Chế độ | Máy làm | Con người làm |
|---|---|---|---|
| Thu thập dữ liệu | Tự động | Thu thập và kiểm chứng BCTC, công bố thông tin, giá | Xem các trường hợp không qua kiểm chứng |
| Sàng lọc | Tự động theo quy tắc cố định | Chạy bộ lọc, giải thích vì sao mã lọt lọc | Viết và sửa quy tắc; mỗi lần sửa được ghi phiên bản |
| Phân tích | Hỗ trợ quyết định | Fact sheet, cờ bất thường, tóm tắt giải trình, có dẫn nguồn | Đọc, đặt câu hỏi, kiểm tra nguồn |
| Quyết định mua bán | Con người quyết | Nêu luận điểm ủng hộ và phản đối kèm dẫn chứng | Tự ghi luận điểm và điều kiện sai trước khi xem đề xuất |
| Định cỡ vị thế | Code tính, người duyệt | Tính theo quy tắc tỷ trọng; chặn nếu vượt hạn mức | Duyệt con số |
| Đặt lệnh | Đề xuất rồi xác nhận từng lệnh | Soạn lệnh, kiểm tra trước lệnh bằng code | Xác nhận từng lệnh; nhập OTP đầu phiên |
| Theo dõi | Máy chạy trong hạn mức, người giám sát | Cảnh báo ít và phân tầng; lệnh thoát đã cam kết trước chạy tự động | Đặt quy tắc thoát lúc mua; có nút dừng |
| Đánh giá lại | Con người chủ trì theo lịch | Lập báo cáo hiệu quả và phân rã lợi nhuận từ nhật ký | Rà soát định kỳ, sửa quy tắc |

### 5.2 Nguyên tắc

- **LLM không chọn mã và không tự quyết định mua bán.** LLM đọc tài liệu, tóm tắt, giải thích; mọi con số do code tính, đúng nguyên tắc ở [architecture.md](../dinh-huong/architecture.md).
- **Hạn mức là code, không phải lời nhắc.** Tỷ trọng tối đa mỗi mã, giá trị tối đa mỗi lệnh, số lệnh tối đa mỗi ngày, lỗ tối đa mỗi ngày: vượt là lệnh bị chặn.
- **Tự động hóa việc ít giao dịch hơn, không phải nhiều hơn.** Ưu tiên tái cân bằng và thoát lệnh theo quy tắc đã cam kết.
- **Ít điểm duyệt, mỗi điểm có trọng lượng.** Người duyệt phải ghi lý do; không biến việc duyệt thành bấm "đồng ý" hàng loạt.
- **Mọi quyết định có nhật ký:** đề xuất của máy, dữ liệu đầu vào, quyết định của người, lý do, kết quả.
- **Backtest chỉ có giá trị khi dùng dữ liệu đúng thời điểm công bố** và nằm ngoài giai đoạn mô hình đã học. Đây là lý do `published_at` và `discovered_at` phải được lưu từ Project 3.

### 5.3 Lộ trình tăng dần mức tự động

| Giai đoạn | Nội dung | Điều kiện sang giai đoạn sau |
|---|---|---|
| 0. Hỗ trợ quyết định | Dữ liệu đã kiểm chứng, sàng lọc, cờ bất thường, cảnh báo (chính là sản phẩm Soi) | Dữ liệu đủ tin cậy trên nhóm mã theo dõi |
| 1. Kỷ luật | Bản chính sách đầu tư cá nhân, nhật ký quyết định, quy tắc tỷ trọng và thoát lệnh | Các quy tắc được viết ra và dùng ổn định |
| 2. Chạy bóng | Hệ thống đề xuất lệnh nhưng không gửi; so sánh với quyết định thật | Đủ dài để thấy đề xuất hợp lý và hạn mức hoạt động đúng |
| 3. Paper trading | Gửi lệnh vào môi trường giả lập | Không có lỗi đặt lệnh; đối soát khớp |
| 4. Tiền thật, vốn nhỏ, xác nhận từng lệnh | Kết nối API của CTCK; mỗi lệnh cần người xác nhận | Chạy ổn định, nhật ký đầy đủ |
| 5. Lệnh thoát cam kết trước chạy tự động | Chỉ các lệnh cắt lỗ, chốt lời, tái cân bằng theo quy tắc đã duyệt | Không mở rộng sang lệnh mua mới tự động |

### 5.4 Liên hệ với đề tài

- Hướng ĐATN đang đề xuất (phát hiện và giải thích bất thường, sàng lọc tăng trưởng có giải thích và backtest) phủ đúng các bước sàng lọc, phân tích và theo dõi, là những bước ngành đã chấp nhận tự động hóa.
- Phần đặt lệnh cho tài khoản riêng là công cụ cá nhân, tách khỏi sản phẩm công khai vì lý do pháp lý.
- Kết quả 1.4 dùng được cho chương đánh giá: chỉ ra vì sao đề tài không đi theo hướng "agent tự giao dịch" và vì sao backtest phải dùng dữ liệu theo đúng ngày công bố.

## 6. Điểm chưa xác minh

- **API tại Việt Nam:**
  - phí dùng API, giới hạn tần suất cụ thể, môi trường thử có API của SSI, DNSE, TCBS;
  - chi tiết xác thực của TCBS và DNSE (chỉ từ tóm tắt tìm kiếm);
  - API cho cá nhân tại VPS, VNDirect, Pinetree, KIS, MBS.
- **Pháp lý Việt Nam:**
  - điều khoản hợp đồng CTCK về bot;
  - thông tư thay Thông tư 134/2017 đã ban hành hay chưa;
  - số điều khoản của Thông tư 99/2020 và Luật Chứng khoán 2019 (chưa đối chiếu văn bản gốc).
- **Vi cấu trúc:** ngày vận hành KRX (2/5 hay 5/5/2025), giới hạn vị thế phái sinh (5.000 hay 4.500 hợp đồng), mức phí trả sở chính xác.
- **Quy trình tổ chức:** công cụ và nhịp làm việc trong bảng mục 2 là thông lệ ngành, không có nguồn riêng cho từng ô. Bộ số 74% / 69% / 6% của Mercer cần mở PDF gốc để chắc thuộc bản 2024.
- **HITL:** số điều khoản RTS 6; chi tiết vụ Knight Capital ngoài con số lỗ và mức phạt; "lỗ tối đa trong ngày" không phải kiểm soát được nêu tên trong quy định nào đã đọc.
- **Công cụ quốc tế:** mô tả các terminal, hệ thống danh mục và công cụ sàng lọc ở mục 1.1 và 1.2 theo hiểu biết chung, không kiểm tra lại; Interactive Brokers có cho đặt lệnh qua MCP hay không.
- **Bằng chứng hành vi:** chưa có nghiên cứu thực nghiệm cho checklist và nhật ký quyết định.

## 7. Nguồn chính

<details>
<summary>Công cụ quốc tế và bằng chứng</summary>

- Bloomberg ASKB: https://www.thetradenews.com/bloomberg-embeds-agentic-ai-into-the-terminal/
- LSEG và Microsoft: https://news.microsoft.com/source/2025/10/12/lseg-and-microsoft-transform-access-to-ai-ready-financial-data-in-customer-workflows/
- ChatGPT for Financial Services: https://www.cnbc.com/2026/09/10/openai-chatgpt-for-financial-services-targets-work-of-junior-bankers.html
- Interactive Brokers và MCP: https://www.interactivebrokers.com/en/general/about/mediaRelations/7-28-26.php
- Alpaca MCP server: https://github.com/alpacahq/alpaca-mcp-server
- Public, agent cho danh mục: https://www.prnewswire.com/news-releases/public-becomes-the-first-brokerage-to-introduce-ai-agents-for-your-portfolio-302729050.html
- TradingAgents: https://github.com/TauricResearch/TradingAgents ; https://arxiv.org/abs/2412.20138
- ai-hedge-fund: https://github.com/virattt/ai-hedge-fund
- Qlib và RD-Agent: https://github.com/microsoft/qlib ; https://github.com/microsoft/RD-Agent
- Magnetar: https://www.hedgeweek.com/magnetar-to-launch-ai-powered-hedge-fund-with-bots-replacing-analyst-teams/
- Vals Finance Agent v2: https://www.vals.ai/benchmarks/fabv2
- FinanceBench: https://arxiv.org/abs/2311.11944
- StockBench: https://arxiv.org/abs/2510.02209
- FINSABER: https://arxiv.org/abs/2505.07078
- Profit Mirage: https://arxiv.org/abs/2510.07920
- Memorization Problem: https://arxiv.org/abs/2504.14765
- Alpha Arena mùa 1: https://protos.com/llm-crypto-trading-contest-finds-llms-cant-trade-crypto/

</details>

<details>
<summary>Quy trình đầu tư</summary>

- CFA Institute, quy trình quản lý danh mục: https://www.cfainstitute.org/sites/default/files/-/media/documents/article/refresher-readings-free/rr-2018-l2v6r47.pdf
- CFA Institute, IPS cho nhà đầu tư cá nhân: https://rpc.cfainstitute.org/policy/positions/elements-of-an-investment-policy-statement-for-individual-investors
- Mercer, khảo sát AI trong quản lý đầu tư: https://www.mercer.com/insights/investments/portfolio-strategies/ai-in-investment-management-survey/
- OMS, EMS, PMS: https://www.limina.com/blog/ems-vs-oms-vs-pms
- Buy-side và sell-side: https://www.wallstreetprep.com/knowledge/sell-side-vs-buy-side-equity-research/
- VCBF: https://www.vcbf.com/quy-mo/cac-quy-mo/quy-dau-tu-co-phieu-hang-dau-vcbf/
- Dragon Capital: https://www.dragoncapital.com/institutional/funds/vef/
- VinaCapital VDEF: https://wm.vinacapital.com/investment-solutions/onshore-funds/vdef/
- Thông tư 99/2020/TT-BTC: https://luatvietnam.vn/tai-chinh/thong-tu-99-2020-hoat-dong-cua-cong-ty-quan-ly-quy-dau-tu-chung-khoan-196329-d1.html
- FiinPro-X: https://fiingroup.vn/vi/fiinpro-x.html

</details>

<details>
<summary>Hạ tầng và pháp lý Việt Nam</summary>

- SSI FastConnect v3: https://developers.ssi.com.vn/docs/getting-started
- SSI FastConnect Trading: https://guide.ssi.com.vn/ssi-products/tieng-viet/fastconnect-trading/huong-dan-ket-noi
- SSI Paper Trading: https://www.ssi.com.vn/khach-hang-ca-nhan/giao-dich-tren-ung-dung-ssi-paper-trading
- DNSE OpenAPI: https://developers.dnse.com.vn
- DNSE Lightspeed API: https://hdsd.dnse.com.vn/san-pham-dich-vu/dnse-lightspeed-api/dnse-lightspeed-api-v2.md
- TCBS Open API: https://developers.tcbs.com.vn/
- Giấy phép vnstock: https://vnstocks.com/onboard/giay-phep-su-dung
- FiinQuant: https://fiinquant.vn/Pricing
- WiGroup WiData: https://www.wigroup.vn/en/widata/pricing
- Algotrade: https://www.algotrade.vn/about ; https://papertrade.algotrade.vn/
- Chu kỳ thanh toán T+2: https://xaydungchinhsach.chinhphu.vn/chu-ky-thanh-toan-chung-khoan-chinh-thuc-rut-ngan-xuong-t2-119220829211822366.htm
- KRX vận hành: https://dantri.com.vn/kinh-doanh/he-thong-krx-chinh-thuc-van-hanh-tu-ngay-55-20250424144532178.htm
- Thời điểm T+0 và bán khống: https://nguoiquansat.vn/lanh-dao-vsdc-tiet-lo-thoi-diem-trien-khai-t-0-va-ban-khong-297283.html
- SSI, hỏi đáp KRX: https://www.ssi.com.vn/khach-hang-ca-nhan/krx-thi-truong-co-so-faq
- Giao dịch thuật toán và khung pháp lý: https://tapchikinhtetaichinh.vn/giao-dich-thuat-toan-va-ham-y-chinh-sach-cho-thi-truong-chung-khoan-viet-nam.html
- Dự thảo thay Thông tư 119 và 134: https://vietstock.vn/2026/07/pho-chu-tich-ubcknn-thay-the-thong-tu-119-va-134-la-can-thiet-de-dap-ung-yeu-cau-nang-hang-143-1465235.htm
- UBCKNN cảnh báo ứng dụng đầu tư: https://www.tinnhanhchungkhoan.vn/uy-ban-chung-khoan-canh-bao-nha-dau-tu-ve-cac-ung-dung-dau-tu-passion-invest-finhay-tikop-infina-savenow-post307190.html
- UBCKNN cảnh báo nhóm khuyến nghị: https://vneconomy.vn/uy-ban-chung-khoan-canh-bao-ve-cac-nhom-chat-phim-hang-lua-ga.htm

</details>

<details>
<summary>HITL và hành vi</summary>

- Feng và cộng sự, Levels of Autonomy for AI Agents: https://arxiv.org/abs/2506.12469
- MiFID II RTS 6: https://eur-lex.europa.eu/eli/reg_del/2017/589/oj/eng
- ESMA, Supervisory Briefing về giao dịch thuật toán (02/2026): https://www.esma.europa.eu/sites/default/files/2026-02/ESMA74-1505669079-10311_Supervisory_Briefing_on_Algorithmic_Trading_in_the_EU.pdf
- SEC Rule 15c3-5: https://www.sec.gov/files/rules/final/2010/34-63241.pdf
- SEC và Knight Capital: https://www.sec.gov/files/litigation/admin/2013/34-70694.pdf
- FINRA Notice 15-09: https://www.finra.org/rules-guidance/notices/15-09
- SEC, hướng dẫn robo-advisor: https://www.sec.gov/investment/im-guidance-2017-02.pdf
- ESMA, copy trading: https://www.esma.europa.eu/sites/default/files/2023-03/ESMA35-42-1428_Supervisory_Briefing_on_Copy_Trading.pdf
- LangGraph interrupts: https://docs.langchain.com/oss/python/langgraph/interrupts
- OpenAI, Practices for Governing Agentic AI Systems: https://cdn.openai.com/papers/practices-for-governing-agentic-ai-systems.pdf
- Goddard và cộng sự, automation bias: https://pmc.ncbi.nlm.nih.gov/articles/PMC3240751/
- Green, The flaws of policies requiring human oversight: https://www.sciencedirect.com/science/article/pii/S0267364922000292
- Buçinca và cộng sự, cognitive forcing: https://www.eecs.harvard.edu/~kgajos/papers/2021/bucinca21trust.pdf
- Barber và Odean (2000): https://faculty.haas.berkeley.edu/odean/papers%20current%20versions/individual_investor_performance_final.pdf
- Odean (1998): https://onlinelibrary.wiley.com/doi/abs/10.1111/0022-1082.00072
- Fischbacher, Hoffmann, Schudy (2017): https://ideas.repec.org/p/knz/dpteco/1410.html
- Lệnh điều kiện của SSI: https://www.ssi.com.vn/upload/files/KHCN/ungdunglenhdk15052023%20moi.pdf

</details>
