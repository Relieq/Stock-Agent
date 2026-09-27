# Tin tức và giá cổ phiếu: góc nhìn và cách làm

> Tài liệu đi kèm [north-star.md](north-star.md). Cập nhật 27/09/2026.
> Các nghiên cứu được tra qua bản tóm tắt kết quả tìm kiếm, chưa đọc toàn văn. Trước khi trích vào báo cáo cần đọc lại bài gốc.

## 1. Kết luận ngắn

- **Tin tức có làm giá biến động, nhưng phần lớn phản ứng diễn ra gần như ngay lập tức**, nên không kịp giao dịch theo.
- **Phần còn khai thác được** chủ yếu nằm ở cổ phiếu nhỏ, kém thanh khoản và sau tin xấu. Phần này **đang co lại** vì ngày càng nhiều người dùng AI để đọc tin.
- **Ở Việt Nam, bằng chứng còn ít**, chủ yếu là các nghiên cứu sự kiện quy mô nhỏ. Dù vậy có vài phát hiện đáng chú ý:
  - giao dịch của người nội bộ tác động rõ tới giá;
  - biên độ giá ±7% khiến phản ứng kéo dài sang phiên sau;
  - tin xấu làm tăng biến động.
- **→ Đừng xây "máy dự đoán giá từ tin tức".** Hãy làm 3 việc khả thi và có giá trị: **giải thích**, **thống kê sự kiện**, và **chấm mức độ quan trọng** của tin. Dự đoán chỉ nên là thí nghiệm nội bộ.

## 2. Bằng chứng

### 2.1 Thế giới

| Nghiên cứu | Phát hiện chính | Ý nghĩa cho Soi |
|---|---|---|
| Tetlock (2007, *Journal of Finance*) | Giọng điệu bi quan của báo chí tạo áp lực giảm giá tạm thời, sau đó giá quay về giá trị cơ bản | Tin tức tác động giống một cú sốc ngắn hạn, không phải lúc nào cũng mang thông tin thật |
| Martineau (2022) và các tranh luận năm 2025 | Ở Mỹ, hiện tượng giá tiếp tục trôi theo chiều kết quả kinh doanh sau ngày công bố (PEAD) gần như đã biến mất với cổ phiếu lớn từ khoảng 2006. Các nghiên cứu năm 2025 vẫn còn tranh luận | Thị trường phát triển hấp thụ tin rất nhanh. Việt Nam chưa có nghiên cứu PEAD nào, và đây là khoảng trống có thể tự nghiên cứu |
| Lopez-Lira & Tang (2023; *JFE* 2026) | Điểm cảm xúc từ GPT dự đoán đúng phản ứng ban đầu, nhưng phần này không giao dịch kịp. Phần giá trôi sau đó chủ yếu có ở cổ phiếu nhỏ và sau tin xấu. **Sharpe của chiến lược giảm từ 6,54 (Q4/2021) xuống 1,22 (đầu 2024)** | Lợi thế từ đọc tin bằng AI mất nhanh khi nhiều người cùng dùng |
| Kirtac & Germano (2024) | Mô hình ngôn ngữ lớn phân loại cảm xúc tin tức tốt hơn FinBERT và phương pháp từ điển | LLM đủ tốt để phân loại tin; phần khó là biến nó thành lợi nhuận |
| Chen, Kelly & Xiu (2022–) | Biểu diễn tin tức bằng LLM ở 16 thị trường, 13 ngôn ngữ vượt các tín hiệu kỹ thuật; giá phản ứng chậm ở nơi khó kinh doanh chênh lệch giá | Thị trường có nhiều rào cản như Việt Nam có thể phản ứng chậm hơn |
| Lopez-Lira, Tang & Zhu (2025); Glasserman & Lin (2023) | LLM **nhớ dữ liệu quá khứ**, nên kiểm thử trên giai đoạn trước mốc huấn luyện của mô hình sẽ cho kết quả ảo | Mọi thí nghiệm phải kiểm trên dữ liệu **sau** mốc huấn luyện của mô hình |

### 2.2 Việt Nam

| Nghiên cứu | Phát hiện chính | Ý nghĩa cho Soi |
|---|---|---|
| Sự kiện trên HOSE 2014–2015 | Có lợi suất bất thường quanh ngày công bố kết quả kinh doanh và cổ tức, trải ra trong khoảng 20 ngày | Tin được hấp thụ chậm, nên cửa sổ đo phải dài hơn 1–2 phiên |
| Giao dịch người nội bộ (IRLE 2023; các nghiên cứu năm 2026, ~4.600 giao dịch ở 111 công ty) | Thông báo mua có lợi suất bất thường dương, thông báo bán thì âm. **Có dấu hiệu rò rỉ thông tin trước các giao dịch bán.** Công ty càng được báo chí đưa tin nhiều thì tác động càng nhỏ | **Radar giao dịch nội bộ có giá trị thật.** Nên ưu tiên loại cảnh báo này |
| Dang và cộng sự (2024), 18.826 công bố thông tin 2008–2023 | Các nhóm tin gắn với biến động giá: **cổ tức tiền mặt, phát hành thêm, niêm yết bổ sung, đăng ký bán của người nội bộ, kết quả bán của người nội bộ** | Dùng làm điểm khởi đầu cho việc chấm mức độ quan trọng |
| Vu và cộng sự (2023), PhoBERT, ~40.000 bài CafeF/VnEconomy/Stockbiz | Phân loại cảm xúc đạt trên 81%. Tin tức không làm thay đổi lợi suất trung bình của chỉ số, nhưng **tin xấu làm tăng biến động** | Phần quản trị rủi ro có thể báo "biến động có thể tăng sau tin xấu" (thông tin, không phải khuyến nghị) |
| ~773.000 bài Facebook 2013–2023 (2025) | Cảm xúc trên mạng xã hội có quan hệ dài hạn với VN-Index | Mạng xã hội có ảnh hưởng, nhưng dữ liệu khó thu thập và nhiễu |
| Bản tái lập trên GitHub, chưa qua bình duyệt (dữ liệu 2016–2026) | Cổ phiếu đóng cửa ở giá trần tăng thêm trung bình khoảng 1,7% ở phiên sau | Biên độ giá chặn bớt phản ứng, phần còn lại dồn sang phiên sau. Cần tự kiểm chứng lại |
| Vo & Phan (2017) | Hành vi bầy đàn trên HOSE, mạnh hơn khi thị trường giảm | Nhiều biến động không có tin nào giải thích, nên "không tìm thấy tin" là một câu trả lời hợp lệ |

Chưa tìm thấy: nghiên cứu PEAD cho Việt Nam; nghiên cứu có bình duyệt về tác động của biên độ giá; bộ dữ liệu chuẩn về cảm xúc tin tài chính tiếng Việt trên HuggingFace. **Đây cũng là cơ hội để tự đóng góp.**

## 3. Bốn cấp độ làm việc với tin tức

| Cấp độ | Là gì | Khả thi (6–9 tháng) | Giá trị cho người dùng | Rủi ro pháp lý | Nằm ở đâu trong sản phẩm |
|---|---|---|---|---|---|
| **1. Thu thập & sắp xếp** | Thu tin kèm giờ đăng, gom tin trùng, gắn đúng mã, phân loại | Cao | Trung bình: bớt quá tải thông tin | Thấp | Chuyên viên tin tức & sự kiện |
| **2. Giải thích** | "Vì sao hôm nay biến động": tách phần do thị trường, do ngành, và phần riêng của mã, rồi nêu các chất xúc tác *có thể* liên quan | Cao | **Cao.** Đây là câu người dùng hỏi nhiều nhất | Thấp, nếu viết là "có thể liên quan" và có nguồn | Người giải thích |
| **3. Đo lường (event study)** | Thống kê phản ứng giá quá khứ theo từng loại sự kiện | Trung bình – cao | Cao, vì dùng để xếp hạng cảnh báo | Thấp, nếu trình bày là thống kê quá khứ | Nhà nghiên cứu định lượng → chấm mức độ quan trọng |
| **4. Dự đoán** | Tín hiệu mua/bán từ tin tức | **Thấp** | Không chắc chắn | **Cao**: gần với tư vấn đầu tư | Chỉ thử nghiệm nội bộ, giao dịch giấy |

## 4. Biến nghiên cứu thành tính năng

**"Vì sao hôm nay biến động?"** (tương tự "Why Is It Moving" của Benzinga, Cortex Digests của Robinhood)
- Nêu phần do thị trường, phần do ngành, phần riêng của mã.
- Liệt kê các sự kiện hoặc tin *có thể liên quan*, kèm nguồn và giờ.
- Nêu thêm dòng tiền khối ngoại và khối lượng so với bình thường.
- Nếu không có thì trả lời thẳng "Không tìm thấy thông tin giải thích". Không bịa lý do.

**Chấm mức độ quan trọng cho cảnh báo** (tương tự các điểm relevance, novelty của RavenPack)
- **Công thức:** điểm = mức liên quan tới danh mục × độ mới (không trùng tin trước) × độ lớn phản ứng giá trong quá khứ của loại sự kiện đó.
- **Giai đoạn đầu:** dùng danh sách từ nghiên cứu của Dang và cộng sự (cổ tức tiền mặt, phát hành, giao dịch nội bộ…).
- **Giai đoạn sau:** thay bằng thống kê tự đo trên dữ liệu thu thập được.

**Thống kê sự kiện** (hiển thị trung lập)
- Ví dụ: *"Trong N lần doanh nghiệp công bố [loại sự kiện] từ năm X, biến động giá 5 phiên sau có trung vị là Y%, tỷ lệ tăng là Z%."*
- Luôn ghi rõ: *"Thống kê quá khứ, không dự báo tương lai."*
- Kèm cỡ mẫu và khoảng tin cậy.

**Radar giao dịch nội bộ nổi bật hơn**, vì nghiên cứu ở Việt Nam cho thấy loại tin này có tác động rõ.

## 5. Thiết kế nghiên cứu (có thể làm một chương trong ĐATN)

### Câu hỏi nghiên cứu
1. Giá cổ phiếu Việt Nam phản ứng thế nào với BCTC quý, xét theo mức "bất ngờ" của lợi nhuận?
   - Phản ứng nhanh hay chậm?
   - Có rò rỉ thông tin trước ngày công bố không?
   - Có hiện tượng giá tiếp tục trôi (PEAD) không?
2. Loại công bố thông tin nào thực sự làm giá biến động? Làm lại và mở rộng nghiên cứu của Dang và cộng sự (2024) bằng dữ liệu 2024–2027.
3. Biên độ giá có làm phản ứng kéo dài không, tức là sau các phiên chạm trần hoặc sàn liên tiếp thì giá diễn biến ra sao?
4. (Tùy chọn) Điểm cảm xúc do LLM chấm cho tin tiếng Việt có liên quan tới lợi suất bất thường không? Chỉ kiểm trên tin xuất hiện **sau** mốc huấn luyện của mô hình.

### Dữ liệu (phải bắt đầu thu từ P3)
- Giờ công bố thông tin, lấy từ radar.
- Tin tức kèm `published_at`.
- Giá cuối ngày, cả giá gốc lẫn giá đã điều chỉnh.
- VN-Index và chỉ số ngành.
- Bảng sự kiện quyền.
- Giữ cả các mã đã hủy niêm yết.

### Phương pháp
- **Mô hình thị trường** ước lượng trên cửa sổ [−250, −30] phiên. Tính lợi suất bất thường tích lũy (CAR) trên ba cửa sổ:
  - [−5, −1]: rò rỉ trước ngày công bố;
  - [0, +1]: phản ứng khi công bố;
  - [+2, +20]: giá tiếp tục trôi.
- **Kéo dài cửa sổ** qua các chuỗi phiên chạm trần hoặc sàn.
- **Báo cáo đầy đủ:** cỡ mẫu, trung vị, tỷ lệ dương, khoảng tin cậy. Kiểm định lại trên dữ liệu ngoài mẫu.

### Danh sách lỗi cần tránh
- **Giờ công bố:** gán mỗi tin vào phiên đầu tiên có thể giao dịch được.
  - Trước giờ mở cửa: tính từ phiên ATO.
  - Trong giờ nghỉ trưa: tính từ 13:00.
  - Sau 14:30: tính từ ATC hoặc phiên hôm sau.
  - Cuối tuần, Tết: tính từ phiên kế tiếp.
- **Nguồn giờ:** dùng giờ công bố của Sở GDCK, không dùng giờ báo đăng lại.
- **Công bố dồn cục:** BCTC quý dồn vào vài ngày gần hạn chót, nên phải loại trừ biến động chung của thị trường và ngành.
- **Nhìn trước tương lai:**
  - dùng số liệu đã điều chỉnh về sau thay cho số liệu tại thời điểm công bố;
  - dùng danh sách VN30 hiện tại cho các giai đoạn quá khứ;
  - để LLM "nhớ" dữ liệu quá khứ.
- **Sai lệch do chỉ giữ mã còn sống:** phải giữ cả các mã đã hủy niêm yết hoặc chuyển sàn.
- **Sự kiện gây nhiễu:** cổ tức bằng cổ phiếu, quyền mua, mùa ĐHCĐ, các mốc FTSE, việc HOSE đổi hệ thống giao dịch năm 2025.
- **Khả năng giao dịch thật:** mã chạm trần hay sàn thì không mua hay bán được; không bán khống được; phải tính phí, thuế và T+2.
- **Kiểm định quá nhiều lần:** thử nhiều loại sự kiện × nhiều cửa sổ thì sớm muộn sẽ "tìm thấy" kết quả ảo. Phải đặt ngưỡng thống kê chặt hơn và kiểm lại ngoài mẫu.

### Đầu ra
- **Một chương đánh giá** trong ĐATN. Đây là đóng góp mới, vì Việt Nam chưa có nghiên cứu PEAD.
- **Tính năng "thống kê sự kiện".**
- **Mô hình chấm mức độ quan trọng** cho cảnh báo.

## 6. Góc nhìn thẳng thắn

- **Với sản phẩm công khai:** giải thích và thống kê thì an toàn và có ích. Tín hiệu mua/bán thì rủi ro pháp lý cao, và bằng chứng cho thấy nó khó bền.
- **Với chính bạn** ("đội ngũ đầu tư của riêng mình"): có thể thử tín hiệu từ tin tức bằng giao dịch giấy. Cần kỳ vọng thấp: lợi thế mất nhanh, còn phí, thuế 0,1%, T+2 và biên độ giá sẽ ăn mòn phần lớn lợi nhuận lý thuyết.
- **Giá trị lớn nhất của mảng tin tức** là giúp người dùng **hiểu chuyện gì đang xảy ra với danh mục của mình và không bỏ lỡ tin quan trọng**. Nó không nằm ở việc đoán giá ngày mai.

## 7. Nguồn

- Tetlock (2007): https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1540-6261.2007.01232.x
- Martineau (2022), PEAD: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3111607
- Lopez-Lira & Tang: https://arxiv.org/abs/2304.07619
- Kirtac & Germano (2024): https://arxiv.org/abs/2412.19245
- Chen, Kelly & Xiu: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4416687
- Lopez-Lira, Tang & Zhu (2025), LLM ghi nhớ dữ liệu: https://arxiv.org/abs/2504.14765
- Giao dịch người nội bộ ở Việt Nam (IRLE 2023): https://www.sciencedirect.com/science/article/abs/pii/S0144818823000157
- Dang và cộng sự (2024), công bố thông tin và giá: https://ebl.vnuhcmjournal.com.vn/index.php/ebl/article/view/1479
- Vu và cộng sự (2023), PhoBERT và VN-Index: https://www.mdpi.com/2227-7072/11/3/101
- Vo & Phan (2017), hành vi bầy đàn: https://www.sciencedirect.com/science/article/abs/pii/S2214635017300035
- Benzinga "Why Is It Moving": https://www.benzinga.com/apis/cloud-product/bz-why-is-it-moving/
- RavenPack news analytics: https://www.ravenpack.com/products/edge/data/news-analytics
