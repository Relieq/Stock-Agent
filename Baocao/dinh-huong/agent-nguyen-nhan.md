# Agent tìm nguyên nhân biến động lợi nhuận

Bản thiết kế, 22/10/2026. Phần tháng 11 trong kế hoạch học kỳ ("phát hiện bất thường trong KQKD, agent tìm nguyên nhân
trong thuyết minh và công văn giải trình"). Thử trên các BCTC quý 3/2026 đã về trước 08/11; đo trên toàn bộ sau mùa.

## 1. Bài toán

Thẻ KQKD cho biết lợi nhuận tăng hay giảm bao nhiêu. Người đọc hỏi tiếp: vì sao? Câu trả lời nằm ở ba chỗ:

1. Chính các dòng của KQKD: mức thay đổi LNST bằng tổng mức thay đổi của các dòng doanh thu, giá vốn, chi phí, thu nhập
   tài chính, lãi công ty liên kết, thuế... Code tính được phần đóng góp của từng dòng mà không cần mô hình.
2. Thuyết minh: mỗi dòng lớn có số thuyết minh (cột TM, hệ thống đã đọc sẵn, ví dụ MSN quý 3 "Tổng doanh thu" là
   thuyết minh 27). Thuyết minh tách dòng đó thành các khoản con (doanh thu theo mảng, thu nhập tài chính gồm lãi tiền
   gửi, lãi tỷ giá, cổ tức...), đủ để biết khoản con nào làm dòng đó đổi.
3. Công văn giải trình: lời của công ty, đã đối chiếu số với BCTC (thẻ đã hiện từ 22/10). Chỉ có khi lợi nhuận đổi từ
   10%, và nhiều nguyên nhân là của một mảng mà BCTC không tách.

Agent ghép ba nguồn thành vài câu "vì sao", mỗi con số có nguồn tới trang, mỗi con số được code kiểm.

## 2. Nguyên tắc (giữ như agent báo cáo)

- Tính sẵn khi BCTC về, không tính lúc người dùng hỏi.
- Code tính số; mô hình chỉ chép bảng thuyết minh và viết câu. Bộ kiểm tra số kiểm mọi con số, chiều tăng/giảm, so sánh.
- Không nguồn thì không nói. Số chép từ thuyết minh chỉ được dùng khi các khoản con cộng lại đúng bằng dòng tương ứng
  trên KQKD đã kiểm chứng (thuyết minh tự trở thành phép kiểm thứ hai, mục 6).
- Không nhận định đầu tư.

## 3. Các bước

```
BCTC đã kiểm chứng
  -> (1) phân rã mức thay đổi LNST theo dòng [code]
  -> (2) chọn dòng cần giải thích [code]: các dòng đóng góp lớn nhất, đủ để giải thích >= 80% mức thay đổi
  -> (3) vòng agent, mỗi bước chọn một công cụ, dừng khi đủ hoặc hết ngân sách:
         - đọc thuyết minh của một dòng (theo số TM)
         - lấy nguyên nhân trong công văn giải trình cho dòng đó (đã đối chiếu)
         - so với cùng dòng của các mã cùng nhóm (ngành chung hay riêng công ty)
         - so với quý trước (đột biến một lần hay xu hướng)
  -> (4) bảng nguyên nhân [code]: mỗi dòng một khoản con hoặc một lý do, có số, nguồn, phần trăm đóng góp
  -> (5) mô hình viết 2-5 câu; bộ kiểm tra số; sai thì viết lại tối đa 2 lần rồi bỏ câu
  -> lưu, hiện trên thẻ ("Vì sao lợi nhuận thay đổi") và cho agent báo cáo dùng
```

### 3.1 Phân rã (code)

Cho mỗi mẫu BCTC, LNST = tổng có dấu của các dòng chính:

- Doanh nghiệp (TT200/TT99): doanh thu thuần, giá vốn, thu nhập tài chính, chi phí tài chính, lãi/lỗ công ty liên kết,
  chi phí bán hàng, chi phí quản lý, lợi nhuận khác, thuế (hiện hành + hoãn lại), lợi ích cổ đông không kiểm soát.
- Ngân hàng (TCTD): thu nhập lãi thuần, lãi thuần dịch vụ, ngoại hối, chứng khoán, hoạt động khác, góp vốn, chi phí
  hoạt động, chi phí dự phòng, thuế.
- Công ty chứng khoán (CTCK): các nhóm doanh thu hoạt động (FVTPL, cho vay ký quỹ, môi giới...), chi phí hoạt động,
  chi phí tài chính, quản lý, thuế.

Đóng góp của dòng = (kỳ này − cùng kỳ) theo dấu của dòng trong công thức. Tổng đóng góp phải bằng mức thay đổi LNST
(ràng buộc kế toán đã kiểm, nên đây là phép cộng chắc chắn đúng); không bằng thì dừng, không giải thích.

### 3.2 Đọc thuyết minh (công cụ chính)

- Tìm trang: thuyết minh nằm sau ba báo cáo. Một lần định vị rẻ: ảnh nhỏ các trang sau LCTT, mô hình trả về số thuyết
  minh bắt đầu ở mỗi trang (giống bước định vị trang hiện có, dùng OpenAI). Kết quả lưu theo tài liệu, dùng lại cho mọi
  dòng.
- Chép: ảnh trang thuyết minh của số TM cần đọc, mô hình chép bảng (tên khoản con, số kỳ này, số cùng kỳ, cột nào là
  quý hay lũy kế) nguyên văn như bước chép bảng hiện có.
- Kiểm: tổng khoản con = dòng trên KQKD ở cùng cột (sai số làm tròn như phép kiểm hiện có). Đạt: khoản con được dùng,
  có nguồn trang. Không đạt: đọc lại một lần ở ảnh nét hơn; vẫn không đạt thì bỏ thuyết minh đó và ghi rõ.
- Thuyết minh quý thường ngắn (nhiều công ty chỉ in lũy kế): cột lũy kế cũng dùng được, khi đó câu ghi rõ "lũy kế".

### 3.3 Vòng agent

LangGraph như agent báo cáo. Trạng thái gồm bảng phân rã, các dòng còn chưa giải thích, ngân sách. Mỗi lượt mô hình
chọn một công cụ cho một dòng, kèm lý do ngắn; code chạy công cụ, cập nhật phần đã giải thích. Dừng khi phần đã
giải thích (theo số, sau khi kiểm) >= 80% mức thay đổi LNST, hoặc đã đọc 4 thuyết minh, hoặc chi phí đạt 0,03 USD.
Lý do có agent thay vì luật cố định: chọn đọc gì phụ thuộc từng công ty (dòng nào lớn, công văn đã nói gì, thuyết minh
có tách mảng hay không); vòng lặp được giới hạn để chi phí và hành vi đoán trước được.

### 3.4 Khi nào chạy

Bộ canh chạy sau khi đọc xong BCTC (sau bước đọc lần hai), cho BCTC đã kiểm chứng có |thay đổi LNST công ty mẹ| >= 10%
hoặc có cờ "cần xem kỹ". Ước 1/2-2/3 số BCTC mỗi mùa.

## 4. Hiển thị

Thẻ KQKD thêm mục "Vì sao lợi nhuận thay đổi" trên mục "Công ty giải thích":
- biểu đồ thác nước: LNST cùng kỳ -> đóng góp từng dòng -> LNST kỳ này (số do code tính);
- 2-5 câu, mỗi số bấm ra trang BCTC hoặc trang thuyết minh;
- phần chưa giải thích được ghi rõ ("còn x tỷ chưa tìm được nguyên nhân trong BCTC").
Email người theo dõi thêm một câu tóm tắt. Agent báo cáo dùng bảng nguyên nhân như một nguồn sẵn có.

## 5. Đo

Đo trên mọi BCTC quý 3/2026 đủ điều kiện sau 08/11, cùng điều kiện cho hai nhà cung cấp:

1. Thuyết minh: tỷ lệ thuyết minh đọc được mà khoản con cộng đúng bằng dòng KQKD (phép kiểm có đáp án sẵn).
2. Phần giải thích được: trung vị % mức thay đổi LNST được giải thích bằng số đã kiểm.
3. So với công văn giải trình (đáp án từ chính công ty, có ở khoảng 1/3 BCTC): các khoản mục công ty nêu có nằm trong
   các dòng agent chọn không; hướng tăng/giảm có khớp không.
4. Bộ kiểm tra số: cấy lỗi vào câu như phép đo agent báo cáo; số câu đúng bị bắt nhầm.
5. Chi phí và thời gian mỗi BCTC.

## 6. Lợi ích phụ: thuyết minh làm phép kiểm thứ hai

Khoản con cộng đúng bằng dòng KQKD là bằng chứng độc lập cho ô đó. Chi phí lãi vay, các dòng không có phép cộng nào
phủ (mục "Thuyết minh làm nguồn ràng buộc thứ hai" trong hướng phát triển) được kiểm theo cách này. Ca MSN quý 3 (dòng
"chi phí đi vay" lệch giữa các kỳ vì công ty đổi cách tính) là loại thuyết minh giải quyết được.

## 7. Chi phí ước tính

Định vị trang thuyết minh khoảng 0,005 USD; mỗi thuyết minh chép 1-2 trang khoảng 0,003-0,006 USD; vòng agent và viết
khoảng 0,003 USD. Khoảng 0,01-0,03 USD mỗi BCTC, dưới 1 USD mỗi mùa VN30. Thử trên 4 BCTC quý 3 đã về (MCH, MSN, TCB,
VPB): dưới 0,2 USD.

## 8. Giả thuyết (bản thiết kế 02/11/2026, chờ duyệt)

**Vì sao cần.** Đoạn nguyên nhân quý 3/2026 (22 BCTC) đúng số nhưng chỉ kể từng dòng KQKD. Câu chuyện chính thường nằm
ở chỗ nhiều dòng cùng đổi một lúc, và đoạn hiện tại không nối các dòng đó lại:
- FPT: lợi nhuận gộp −2.255 tỷ, phần của cổ đông không kiểm soát 467 → 6,2 tỷ, lãi công ty liên kết +666 tỷ;
- MWG: phần của cổ đông không kiểm soát 12,8 → 427 tỷ;
- GVR: tiền bồi thường 1.779 tỷ; VIC: doanh thu tài chính −27.594 tỷ;
- STB: thu dịch vụ 673 → 4.255 tỷ cùng lúc dự phòng 1.044 → 5.729 tỷ.

**Nguyên tắc.**
- Danh sách giả thuyết cố định. Code quyết định giả thuyết nào hiện, theo ngưỡng số; mô hình không tự nghĩ giả thuyết.
- Câu do code điền theo mẫu, không gọi mô hình (0 USD). Mỗi số bấm ra trang BCTC như các số khác.
- Mỗi giả thuyết có nhãn "giả thuyết, chưa kiểm chứng". Nếu có lý do của công ty thì đặt ngay cạnh: công văn nói cùng
  ý thì ghi "công ty xác nhận"; nói khác thì ghi "công ty giải thích khác"; không có công văn thì ghi "công ty chưa nêu".
- Mỗi giả thuyết nói rõ điều gì sẽ xác nhận hoặc bác bỏ nó (ví dụ "thuyết minh về công ty con cuối kỳ").
- Không nhận định tốt/xấu, không nói về giá cổ phiếu.

**Bốn loại.**

| Loại | Code bật khi | Câu mẫu (rút gọn) |
|---|---|---|
| Đổi phạm vi hợp nhất | phần của cổ đông không kiểm soát đổi ít nhất gấp 3 lần (hoặc giảm còn dưới 1/3), cộng thêm ít nhất một dấu hiệu: lãi công ty liên kết đổi ít nhất gấp 3 lần, có dòng LCTT về mua/bán công ty con, hoặc doanh thu và chi phí bán hàng cùng giảm trên 20% | "Nhiều dòng cùng đổi một lúc (…), giống trường hợp công ty thay đổi phần sở hữu ở công ty con" |
| Khoản một lần | thu nhập khác, doanh thu tài chính hoặc chi phí tài chính đổi một lượng bằng ít nhất 1/3 mức thay đổi LNTT và ít nhất 10% LNTT, theo cả hai chiều (cờ hiện tại chỉ xét lợi nhuận khác tăng) | "Phần lớn mức thay đổi đến từ … — khoản ngoài hoạt động chính, thường không lặp lại" (kèm khoản con thuyết minh nếu đã đọc, ví dụ tiền bồi thường) |
| Lãi gộp: quy mô hay biên | lợi nhuận gộp là dòng đóng góp lớn nhất. Code tách mức đổi thành phần do doanh thu đổi (theo biên cùng kỳ) và phần do biên lãi gộp đổi; hai phần cộng đúng bằng mức đổi | "Lợi nhuận gộp tăng X: Y do doanh thu tăng, Z do biên lãi gộp tăng từ a% lên b%" (đây là số tính được, không phải giả thuyết, nhưng đặt cùng chỗ) |
| Ngân hàng: dòng tăng/giảm khác thường | thu dịch vụ, dự phòng hoặc lãi thuần hoạt động khác của quý cao hơn gấp đôi trung bình 4 quý trước của chính ngân hàng đó | "Khác hẳn các quý trước (trung bình …); có thể có khoản một lần" |

**Đo trước khi mở cho mọi người.**
1. Chạy trên mọi BCTC quý đã kiểm chứng (Q4/2025 đến Q3/2026), đếm số lần mỗi loại bật.
2. Đọc từng ca và ghi đúng/sai. Với các BCTC có công văn, đếm số ca công văn xác nhận và số ca công văn nói khác.
3. Chỉnh ngưỡng trên nửa số ca, đo lại trên nửa còn lại (cách đã làm với bộ kiểm tra của agent báo cáo).
4. Chỉ quản trị thấy cho đến khi người dùng duyệt kết quả đo; sau đó mới hiện cho mọi người, có nhãn rõ ràng.

## 9. Thứ tự làm

1. Phân rã bằng code cho ba mẫu, có test (không tốn tiền).
2. Định vị và chép thuyết minh, kiểm tổng; thử trên 4 BCTC quý 3.
3. Vòng agent, bảng nguyên nhân, viết và kiểm.
4. Hiển thị trên thẻ, email, nối với agent báo cáo.
5. Sau 08/11: đo trên toàn bộ quý 3, đưa vào báo cáo kỹ thuật.
