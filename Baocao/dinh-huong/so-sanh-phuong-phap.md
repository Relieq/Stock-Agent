# So sánh các phương pháp trích xuất số từ BCTC

Tài liệu làm việc (22/10/2026). Mục tiêu: thay phần "Hệ thống của khóa trước" trong báo cáo kỹ thuật bằng một so sánh
**theo phương pháp**, đo trên cùng tài liệu, cùng đáp án, cùng thước đo. Hệ thống Stock Report Agent chỉ là một cách cài
đặt của một họ phương pháp, không phải đối tượng so sánh.

Quy ước: [đã kiểm] = đã đọc tận nguồn hoặc tự chạy; [chưa kiểm] = chỉ thấy ở nguồn thứ cấp hoặc suy luận, phải xác minh
trước khi đưa vào báo cáo.

---

## 1. Các họ phương pháp

Đặc điểm chung của BCTC Việt Nam gây khó cho mọi phương pháp:

- Đa số là bản scan (in, ký, đóng dấu, chụp lại): 52/58 file VN30 quý 2/2026 là scan hoặc có lớp chữ OCR rác [đã kiểm, số
  của dự án]. Có file chỉ 72 dpi (GVR bán niên 2026), trang lộn ngược (VHM quý 4/2025), trang ngang xoay 90/270 độ.
- Hai kiểu dấu phân cách hàng nghìn (`1.234.567` và `1,234,567`, khoảng 1/4 file dùng kiểu sau), số âm trong ngoặc
  `(1.234)`, dấu gạch `-` nghĩa là 0/trống, đơn vị đồng / nghìn đồng / triệu đồng.
- Tên chỉ tiêu dài, xuống dòng; cột "Mã số", "Thuyết minh" xen giữa; bảng thường không kẻ ô (ngân hàng) hoặc kẻ ô đầy đủ
  (PLC); 4–6 cột số (quý này, quý năm trước, lũy kế hai năm; cuối kỳ, đầu năm).
- Tiếng Việt có dấu: dấu nhỏ, dễ mất khi ảnh mờ hoặc nén [nguồn: khảo sát OCR tiếng Việt, xem (b)].

Điều quan trọng cho bài toán này: **sai chữ ở tên chỉ tiêu ít hại; sai một chữ số, mất dấu ngoặc, hay đặt đúng số vào sai
dòng/cột mới hại**. Vì vậy thước đo phải là độ đúng theo ô (dòng × cột), không phải tỷ lệ lỗi ký tự hay "túi số".

### (a) Dùng lớp chữ có sẵn trong PDF (PyMuPDF, pdfplumber, Camelot)

- Cách làm: đọc chữ và tọa độ từ PDF, gom thành hàng theo tung độ, xếp số vào cột theo mép phải; Camelot/pdfplumber có chế
  độ bảng kẻ ô (lattice) và bảng không kẻ (stream).
- Mạnh: chính xác tuyệt đối khi lớp chữ là chữ gốc; miễn phí, nhanh (dưới 1 giây/trang), không cần GPU; giấy phép thoáng
  (PyMuPDF: AGPL hoặc thương mại [chưa kiểm phiên bản hiện tại]; pdfplumber MIT; Camelot MIT [chưa kiểm]).
- Yếu: **không áp dụng được cho phần lớn BCTC**: trong 119 BCTC của dự án chỉ 5 file có chữ gốc [đã kiểm, mục 5.2 báo cáo];
  lớp chữ do máy OCR tạo (TIG quý 2/2026) có lỗi chính tả và số bị tách vỡ (`29.137.1.108.932`) [đã kiểm]. Phải tự đánh
  giá chất lượng lớp chữ, không chỉ xem có hay không.
- Vai trò trong thí nghiệm: là **nguồn đáp án** (Soi đã dùng), và là "phương pháp" có độ phủ thấp; báo cáo độ phủ trên tổng
  thể chứ không báo độ đúng (trên file chữ gốc nó đúng 100% theo định nghĩa).

### (b) OCR cổ điển + dựng bảng bằng luật (Tesseract `vie`, PaddleOCR, VietOCR)

- Cách làm: phát hiện dòng chữ, nhận dạng từng dòng, trả về chữ kèm hộp tọa độ; sau đó dùng luật như (a) để gom hàng/cột.
  VietOCR là bộ nhận dạng dòng (CNN + Transformer/seq2seq) thường ghép với bộ phát hiện của PaddleOCR
  ([viblo](https://viblo.asia/p/deepdoc-vietocr-cong-cu-ocr-cho-tieng-viet-nhanh-va-tiet-kiem-chi-phi-2vJPdGO8JeK),
  [bmd1905/vietnamese-ocr](https://github.com/bmd1905/vietnamese-ocr)).
- Mạnh: miễn phí, chạy cục bộ, Tesseract chạy CPU trên Windows; có điểm tin cậy cho từng từ (dùng để chọn ô cần đọc lại);
  kết quả lặp lại được (không ngẫu nhiên).
- Yếu trên BCTC scan:
  - Dấu tiếng Việt dễ mất/nhầm khi ảnh mờ, độ phân giải thấp, nén mạnh
    ([khảo sát OCR tiếng Việt](https://www.themoonlight.io/fr/review/a-survey-on-vietnamese-document-analysis-and-recognition-challenges-and-future-directions)).
    Hướng dẫn Tesseract tiếng Việt khuyên scan 200–400 dpi; dữ liệu huấn luyện dựng cho vài phông phổ biến
    ([vietunicode](https://vietunicode.sourceforge.net/howto/tesseract-ocr.html)) [nguồn cũ, chưa kiểm với tessdata_best].
  - Với số: nhầm `.`/`,` (đổi nghĩa phân cách), mất ngoặc âm, nhầm 1/7, 3/8, 0/6 ở ảnh 72 dpi, dính hai số liền cột.
  - Dựng bảng bằng luật hay vỡ khi tên chỉ tiêu xuống dòng, cột Thuyết minh rỗng, bảng không kẻ, trang xoay; phải tự xoay
    trang trước (Tesseract OSD).
  - PaddleOCR PP-OCRv5 có mô hình đa ngôn ngữ chọn bằng tham số ngôn ngữ
    ([tài liệu PaddleOCR](https://www.paddleocr.ai/latest/en/version3.x/algorithm/PP-OCRv5/PP-OCRv5_multi_languages.html));
    chất lượng với chữ Việt có dấu [chưa kiểm]. Giấy phép Apache 2.0 [nguồn thứ cấp: wikidocs.net/441164].
  - VietOCR (pbcquoc): giấy phép [chưa kiểm, không tìm thấy file LICENSE qua tìm kiếm]. Lưu ý trùng tên với VietOCR
    trên SourceForge (giao diện cho Tesseract, Apache 2.0).
- Chi phí: 0 USD; tốc độ Tesseract vài giây/trang trên CPU [chưa đo]; PaddleOCR/VietOCR chạy CPU được nhưng chậm hơn, GPU
  giúp nhiều [chưa đo].

### (c) OCR + mô hình ngôn ngữ văn bản sắp xếp thành bảng

- Cách làm: OCR (b) hoặc bộ chuyển đổi (d) cho ra văn bản/markdown; một mô hình ngôn ngữ (chỉ đọc chữ, không xem ảnh) đọc
  văn bản đó và trả JSON theo schema (dòng, mã số, các cột).
- Mạnh: mô hình sửa được lỗi bố cục (ghép tên xuống dòng, xác định cột nào là quý/lũy kế, nhận ra dòng tổng); đọc văn bản rẻ
  hơn đọc ảnh nhiều lần (hệ thống Stock Report Agent ghi 272.054 token vào mỗi báo cáo, 0,04 USD với Gemini 2.5 Flash Lite [đã kiểm: bảng
  chi phí trong báo cáo IT3940E của tác giả, bản lưu ở D:/Project 3/report]).
- Yếu: **mô hình không thấy ảnh nên không sửa được chữ số OCR đọc sai**; ngược lại có thể "sửa" số cho khớp ý nó (đổi số,
  tự cộng) mà không có cách phát hiện nếu không có phép kiểm. Đúng số nhưng gán sai dòng là lỗi điển hình khi OCR làm vỡ thứ
  tự hàng. Nếu giao cho mô hình cả việc đổi đơn vị và dấu (như cách làm của Stock Report Agent: nhân ×1.000.000, đổi
  `(100)` thành `-100` bằng mô hình [đã kiểm, README của repo]) thì thêm một nguồn lỗi số học.
- Chi phí: OCR miễn phí + vài phần trăm cent mỗi BCTC cho mô hình văn bản rẻ.

### (d) Mô hình cấu trúc bảng / bộ chuyển đổi tài liệu (Table Transformer, Docling, Marker, MinerU, Nougat-like)

- Cách làm: mô hình bố cục tìm vùng bảng, mô hình cấu trúc bảng dự đoán lưới hàng/cột (Table Transformer
  [PubTables-1M, CVPR 2022](https://arxiv.org/pdf/2110.00061); TableFormer trong Docling), OCR điền chữ vào ô; xuất markdown/
  HTML. Nougat và các mô hình "ảnh → markdown" đầu-cuối thuộc nhóm này nhưng huấn luyện chủ yếu trên bài báo khoa học.
- Docling: giấy phép MIT, mô hình bố cục DocLayNet + TableFormer, OCR tùy chọn (bản đầu dùng EasyOCR, chậm trên CPU,
  "trên 30 giây/trang") ([Docling technical report](https://arxiv.org/html/2408.09869v5)); hỗ trợ Tesseract ở bản sau
  [nguồn thứ cấp]. Stock Report Agent dùng Docling + Tesseract `vie`, đọc lại ô số tin cậy thấp bằng Surya [đã kiểm, README].
- Marker (dùng Surya): mã nguồn GPL-3.0, trọng số mô hình CC-BY-NC-SA với miễn trừ cho tổ chức dưới 5 triệu USD doanh
  thu/vốn và không cạnh tranh với Datalab ([README bản sao](https://github.com/sddai/markerPDF)); có tin Marker 2.0 chuyển
  sang Apache 2.0 nhưng trọng số Surya vẫn giới hạn thương mại
  ([particula.tech](https://particula.tech/blog/docling-vs-mineru-vs-marker-pdf-parser)) [chưa kiểm].
- MinerU: giấy phép có tranh cãi giữa các phiên bản (AGPL-3.0 ở bản cũ; "Apache 2.0 + điều kiện" ở bản mới theo
  [wikidocs](https://wikidocs.net/441164)) [chưa kiểm].
- Mạnh: giữ cấu trúc bảng tổng quát, cục bộ, miễn phí; các hệ PaddleOCR-VL, MinerU đứng cao trên OmniDocBench
  ([OmniDocBench, CVPR 2025](https://arxiv.org/html/2412.07626v2); [bảng xếp hạng cộng đồng](https://www.codesota.com/ocr/benchmark/omnidocbench)
  [nguồn thứ cấp]). Bài OmniDocBench ghi nhận mô hình chuyên dụng thắng trên tài liệu chuẩn, còn VLM đa năng bền hơn trên
  tài liệu khó; trên bản chụp lại thực tế Real5-OmniDocBench, Marker 60,10 điểm so với Qwen3-VL-235B 88,90
  ([arXiv 2603.04205](https://arxiv.org/pdf/2603.04205)) [số do tác giả công bố].
- Yếu trên BCTC: bảng không kẻ của ngân hàng hay bị gộp/tách cột sai; cột "Mã số"/"Thuyết minh" bị nhập vào số; trang ngang
  xoay; chất lượng chữ Việt phụ thuộc OCR bên dưới; cần GPU để có tốc độ chấp nhận được (CPU chạy được nhưng chậm, tính
  bằng chục giây/trang [chưa đo]). Thước đo của các benchmark này (TEDS, điểm tổng hợp) không đo đúng từng số.

### (e) Mô hình ngôn ngữ đọc ảnh, chép thẳng (cách của Soi)

- Cách làm: gửi ảnh trang cho VLM, yêu cầu chép nguyên văn từng ô vào JSON theo schema; code phân tích số, đơn vị, dấu; phép
  kiểm kế toán (tổng, cân đối, giữa các kỳ) quyết định số có được dùng; ô sai được định vị bằng ràng buộc rồi đọc lại.
- Mạnh: đọc được bảng nhiều cột, tên xuống dòng, chữ có dấu, trang xoay (sau khi xoay ảnh) mà không cần bước dựng bảng; một
  mô hình cho mọi mẫu biểu; không cần GPU. Trên 11 BCTC có đáp án: 99,94% ô đúng ở ảnh gốc, 100% ở 200/120 dpi, 98,8% ở
  72 dpi [đã kiểm, bảng tab:dapan; phải chạy lại trước khi dùng].
- Yếu: không có điểm tin cậy từng ô; đôi khi "bịa" hoặc chép lệch một dòng; kết quả không lặp lại tuyệt đối; tốn tiền theo
  token ảnh (0,12 USD/BCTC tính cả đọc lại [đã kiểm, mục chi phí]); phụ thuộc nhà cung cấp (giảm bằng hai nhà cung cấp).

### (f) Lai ghép

- Ví dụ: OCR cổ điển trước, chỉ gửi ảnh vùng tin cậy thấp cho VLM (Stock Report Agent làm biến thể OCR→OCR: Tesseract rồi
  Surya cho ô tin cậy thấp); hoặc VLM trước, OCR làm "người đọc thứ hai" độc lập rẻ; hoặc dùng lớp chữ khi có chữ gốc, VLM
  khi không. Soi hiện là lai theo nghĩa: VLM chép + code kiểm + đọc lại có chọn lọc + người đọc thứ hai khác hãng.
- Điểm mấu chốt cho so sánh: **phép kiểm kế toán không phụ thuộc phương pháp đọc**, áp được cho đầu ra của mọi họ (a)–(e).
  Vì vậy thí nghiệm nên tách hai câu hỏi: (1) phương pháp đọc đúng bao nhiêu ô; (2) phép kiểm bắt được bao nhiêu phần lỗi
  của từng phương pháp.

---

## 2. Bộ vnpdf

[đã kiểm: tải tập parquet 22/10/2026 và đọc mã nguồn benchmark]

- Nguồn: [kiethuynhanh/vnpdf-financial-reports-dataset](https://huggingface.co/datasets/kiethuynhanh/vnpdf-financial-reports-dataset)
  trên Hugging Face, giấy phép MIT, không giới hạn truy cập, tác giả Kiet Huynh Anh (không phải tác giả Stock Report Agent).
- Nội dung: 401 trang của **9 BCTC hợp nhất quý 4/2024** (AAA 27, ACB 26, FPT 35, MBB 42, MWG 37, SHB 30, TCB 65, VIB 61,
  VPB 78 trang). Phần lớn là trang thuyết minh: chỉ khoảng 19 trang chứa tiêu đề BCĐKT/KQKD/LCTT theo tìm từ khóa (trang nối
  tiếp không có tiêu đề nên con số thật cao hơn một ít).
- Mỗi dòng gồm: `image` (ảnh PNG cạnh dài **512 px**, khoảng 44 dpi cho trang A4 — chỉ là ảnh thu nhỏ), `text` (văn bản
  trang dạng bảng markdown `|...|`), `custom_id`, `page_number`, `report_id`.
- Đáp án là **văn bản cả trang**, không phải bảng ô có dòng/cột/mã số. Cách tạo văn bản không được ghi rõ ("extracting
  text ... validating and cleaning"); kiểu markdown và dấu vết `NOT_SELECTED` gợi ý do một công cụ phân tích tài liệu tạo
  ra, có thể từ PDF chữ gốc [chưa kiểm]. Ảnh mẫu VIB trông như PDF xuất thẳng (chữ sắc, không nghiêng).
- Benchmark của Stock Report Agent (`evaluation/ocr_benchmark`): không dùng ảnh 512 px trong tập mà dựng lại ảnh 300 dpi
  từ PDF gốc đặt tại một thư mục cục bộ (không có trong repo), có bảng lệch số trang theo công ty. Ba thước đo: CER sau khi
  bỏ định dạng, tỷ lệ từ tìm thấy, và **Number F1 = F1 trên "túi số" của cả trang** (đếm số trùng không quan tâm vị trí).
  Nghĩa là đúng số nhưng sai dòng/cột vẫn được tính đúng; số trên trang thuyết minh được tính như số trên bảng chính.
- Kết luận dùng được không:
  - Dùng được về pháp lý (MIT, ghi nguồn).
  - **Không dùng được làm đáp án theo ô** như bộ đáp án chữ gốc của Soi: không có cấu trúc dòng/cột, phần lớn là thuyết
    minh, ảnh trong tập quá nhỏ, nguồn văn bản chưa rõ.
  - Dùng được theo hai cách phụ: (1) để báo **Number F1 trên cùng thước đo** khi cần đặt số của Soi cạnh số đã công bố của
    các công cụ OCR (chỉ trên các trang ba báo cáo chính); (2) 9 BCTC quý 4/2024 này là ứng viên mở rộng bộ đáp án chữ gốc:
    tải PDF gốc từ Vietstock, kiểm lớp chữ là chữ gốc (như đã làm với TIG), nếu đạt thì thêm vào bộ đáp án — thêm FPT, MWG,
    MBB, TCB, SHB, VIB, AAA (hiện bộ đáp án chỉ có 4 công ty). Đây là bước riêng, chi phí khoảng 0,1 USD/BCTC cho 4 mức ảnh.
- Bản sao cục bộ: không có trong `Data/` hay `Code/eval/` (chỉ có nhắc tên trong README, architecture.md,
  vision-and-roadmap.md và mục "Hướng phát triển" của báo cáo). Bản tải để kiểm tra nằm ở thư mục tạm, không đưa vào repo.

---

## 3. Những gì Soi đã có để đo trực tiếp

- Bộ đáp án chữ gốc: 11 BCTC, 4 công ty (VPB 5, ACB 1, GVR 1, PLC 4), 3.107 ô [số trong báo cáo, phải chạy lại]. Gồm 6 BCTC
  trong kho (đo bằng `measure`/`degraded --doc-id`: 6, 160, 162, 5829, 6070, 13892) và 5 file ngoài kho
  (`Data/raw/born_digital/set.json`: VPB Q3/2025, PLC Q2, Q3, Q4/2025, Q2/2026; TIG bị loại).
- Bản làm mờ: `degrade()` dựng PDF chỉ có ảnh ở 3 mức (200 dpi sạch; 120 dpi mờ + nhiễu + nghiêng 0,7°; 72 dpi mờ + nghiêng
  1,2° + JPEG 35), hạt giống ngẫu nhiên cố định → mọi phương pháp nhận **đúng cùng ảnh**.
- Kết quả đọc đã lưu: `Data/raw/born_digital/runs/*_{goc,tot,vua,xau}.json` (Haiku 5.5). Mỗi bản ghi giữ danh sách sửa
  (`repairs` với `before`/`after`/`accepted`), nên có thể dựng lại kết quả **lần đọc đầu, chưa tự sửa** mà không gọi mô
  hình (cần kiểm mọi thay đổi ở bước leo thang đều được ghi lại — `labels_repaired`, `codes_inferred` cũng là thay đổi).
- Bộ chấm `compare_record(record, doc)`: nhận một bản ghi dạng Soi (mỗi báo cáo: `columns` có `kind`, `rows` có `code`,
  `label`, `page`, `values`) và PDF chữ gốc; ghép dòng theo mã số rồi theo tên; đếm đúng/sai/thiếu/thừa, dòng bỏ sót; "0" và
  trống tính như nhau. Bộ kiểm `_check(record)` + `flagged()` cho biết BCTC có bị báo hay không.
- Hệ quả: **bất kỳ phương pháp nào, chỉ cần viết bộ chuyển đầu ra sang dạng bản ghi này, là được chấm bằng cùng bộ chấm và
  cùng phép kiểm**. Đây là khung cho thí nghiệm.

Lưu ý thiên lệch đã có: cách dựng đáp án (gom chữ theo hàng, số theo mép phải) giống cách dựng bảng của (a)/(b). Đáp án
được chọn theo số dòng ghép được, không theo số khớp, nên không thiên về Soi; nhưng phương pháp (b) dùng cùng luật gom hàng
sẽ được lợi về cấu trúc. Ghi rõ trong phần giới hạn.

---

## 4. Thiết kế thí nghiệm

### 4.1 Câu hỏi

1. Trên cùng ảnh trang, mỗi phương pháp đọc đúng bao nhiêu ô (theo dòng × cột), ở từng mức chất lượng ảnh?
2. Khi áp cùng bộ phép kiểm kế toán của Soi lên đầu ra của mỗi phương pháp, bao nhiêu ô sai bị báo, bao nhiêu lọt?
3. Chi phí (USD, thời gian, phần cứng) mỗi BCTC.

### 4.2 Phương pháp đưa vào (5 + 1 tùy chọn)

| # | Phương pháp | Đại diện cho | Cách cài | Gọi mô hình trả tiền? |
|---|---|---|---|---|
| M1 | Lớp chữ PDF | (a) | PyMuPDF, đã có | Không |
| M2 | Tesseract 5 `vie` (tessdata_best) + dựng bảng bằng luật | (b) | Tesseract cho Windows (bản UB Mannheim) + gói `vie`; dựng bảng bằng chính luật gom hàng của bộ đáp án áp lên hộp chữ OCR | Không |
| M3 | Docling (+ Tesseract `vie`, TableFormer) → bảng markdown → luật ánh xạ cột | (d) | `pip install docling`; CPU được, GPU nhanh hơn | Không |
| M4 | OCR (đầu ra M3, hoặc M2 nếu M3 hỏng) + mô hình văn bản sắp thành JSON cùng schema của Soi | (c) | Prompt chép bảng của Soi, thay ảnh bằng văn bản OCR; cùng mô hình Haiku 5.5 | Có |
| M5a | VLM chép thẳng, một lần, chưa tự sửa | (e) | Dựng lại từ kết quả đã lưu (hoàn nguyên `repairs`) | Không (đã trả) |
| M5b | Soi đầy đủ: VLM + kiểm + định vị + đọc lại | (e)+(f) | Kết quả đã lưu | Không (đã trả) |
| M6 (tùy chọn) | VLM mở chạy cục bộ (ví dụ Qwen2.5-VL 7B qua Ollama) | (e) mở | Máy có RTX 5050 8 GB và Ollama | Không |

Lý do chọn: mỗi họ có một đại diện phổ biến, miễn phí hoặc rẻ, giấy phép dùng được cho nghiên cứu. Bỏ Marker/MinerU khỏi
bộ chính vì giấy phép trọng số chưa rõ và cài nặng; có thể thêm sau như M3'. M4 dùng cùng mô hình với M5 để so sánh tách
được "đọc ảnh" và "đọc văn bản OCR" — khác biệt chỉ ở đầu vào. M5a so với M5b đo phần đóng góp của bước tự sửa. Nếu chọn
M4 với gpt-5.4-mini thì phải chạy cả M5 với gpt-5.4-mini mới công bằng (đắt hơn ~5 lần, không cần cho câu hỏi chính).

### 4.3 Dữ liệu

- 11 BCTC chữ gốc × 4 mức ảnh (ảnh gốc dựng ở 200 dpi không làm mờ / tốt 200 / vừa 120 / xấu 72) = 44 lượt cho mỗi phương
  pháp. Lưu ý: "ảnh gốc" của Soi là ảnh dựng từ trang PDF theo cách của hệ thống thật; các phương pháp khác phải nhận đúng
  ảnh đó (ghi ra PNG một lần, dùng chung), không được đọc lớp chữ.
- Cố định trang: mọi phương pháp dùng **cùng danh sách trang ba báo cáo** mà Soi đã định vị (lấy từ bản ghi), để không trộn
  lỗi tìm trang vào lỗi đọc số. Ghi riêng một dòng: phương pháp nào tự tìm trang được thì độ đúng tìm trang là bao nhiêu.
- Cố định xoay trang: dùng cùng góc xoay đã biết cho mọi phương pháp (Tesseract OSD chỉ báo thêm, không thay).
- Nếu muốn rộng hơn: thêm các BCTC quý 4/2024 trong bộ vnpdf có PDF chữ gốc (mục 2), làm sau, chi phí riêng.

### 4.4 Thước đo

Chính (cùng bộ chấm `compare_record`, cùng quy ước 0 = trống):

- **Độ đúng theo ô** = ô đúng / (ô có số trong đáp án ∪ ô có số trong đầu ra). Tách: sai số, thiếu (bỏ sót), thừa (số ở ô
  trống), dòng không ghép được, dòng đáp án bị bỏ sót.
- **Ô sai bị báo / lọt**: áp `_check` + `flagged` lên bản ghi của từng phương pháp; ô sai nằm trong BCTC bị báo là "hệ thống
  tự biết"; ô sai trong BCTC không bị báo là "lỗi im lặng". Báo theo nghìn ô.
- **BCTC đạt kiểm chứng**: tỷ lệ BCTC qua mọi phép kiểm bắt buộc mà không cần người.

Phụ (để đặt cạnh số đã công bố của công cụ OCR): Number F1 kiểu "túi số" trên văn bản ba báo cáo chính, tính bằng đúng công
thức của benchmark vnpdf (MIT, ghi nguồn). Viết rõ trong báo cáo vì sao hai thước đo khác nhau: túi số không phạt đúng số sai
dòng/cột.

Chi phí: USD (theo bảng giá trong mã, tính từ token thật), thời gian thực mỗi BCTC, phần cứng.

### 4.5 Ước tính chi phí

- M1, M2, M3, M6: 0 USD (chạy cục bộ).
- M5a, M5b: 0 USD (chấm lại kết quả đã lưu).
- M4 (Haiku 5.5: 0,10 USD/triệu token vào, 0,50 USD/triệu token ra): mỗi BCTC khoảng 3 báo cáo × (6–10 nghìn token văn bản
  OCR vào + 4–6 nghìn token JSON ra) ≈ 25 nghìn vào + 15 nghìn ra ≈ 0,01 USD. 44 lượt ≈ **0,45 USD**; cộng 1–2 lần chạy thử
  trên 1 BCTC khi viết prompt ≈ 0,05 USD. Tổng **khoảng 0,5 USD**, dưới 1 USD. (Đối chiếu: lượt chép ảnh của Soi trên các
  bản làm mờ tốn 0,008–0,026 USD mỗi BCTC khi không phải đọc lại [đã kiểm, `usd` trong kết quả đã lưu].)
- Không chạy bước định vị/đọc lại cho M4 (đó là phần của Soi); nếu muốn đo "M4 + tự sửa của Soi" thì bước đọc lại phải đọc
  ảnh, tức đã thành lai — để làm thí nghiệm phụ.

### 4.6 Cài đặt cần có

- Windows, không Docker: PyMuPDF (đã có), Tesseract 5 + `vie.traineddata` (tessdata_best), `pytesseract`; Docling (kéo theo
  PyTorch, ~2 GB). Rủi ro: Smart App Control đã chặn DLL libpq từ 12/10, có thể chặn DLL của PyTorch/Tesseract [chưa kiểm];
  khi đó chạy trong container Linux (thêm `tesseract-ocr tesseract-ocr-vie` và docling vào một image riêng, không đụng image
  `soi-app` đang chạy).
- GPU: máy có RTX 5050 Laptop 8 GB (nvidia-smi). Docling và M6 dùng được GPU trên Windows nếu Smart App Control cho phép;
  trong Docker cần NVIDIA Container Toolkit qua WSL2 [chưa kiểm]. Không bắt buộc: chạy CPU chỉ chậm hơn (ước tính vài chục
  giây/trang với docling [chưa đo]).
- Mã cần viết (một script đo mới, ví dụ `eval/methods.py`): xuất ảnh dùng chung; bộ chuyển đầu ra M2/M3/M4/M6 sang dạng bản
  ghi của Soi (cột theo `kind`, dòng có `code`/`label`/`page`/`values` là chuỗi như in); gọi `compare_record` và `flagged`;
  lưu kết quả mỗi lượt để chấm lại miễn phí.

### 4.7 Đe dọa tính hợp lệ và cách giảm

- **Đáp án sạch hơn bản scan thật**: file chữ gốc in phông máy, không con dấu, không nếp gấp; mức làm mờ chỉ mô phỏng. Ghi
  rõ; giữ cùng ước tính trên 119 BCTC của Soi làm bằng chứng bổ sung (chỉ cho Soi, vì các phương pháp khác chưa chạy trên tổng
  thể).
- **Ít công ty**: 4 công ty, VPB chiếm 5/11. Báo kết quả theo từng công ty và theo ngân hàng / doanh nghiệp thường; mở rộng
  bằng vnpdf nếu PDF gốc đạt.
- **Thiên lệch cấu trúc**: luật dựng đáp án trùng luật dựng bảng của M2 → M2 có lợi; ghi rõ.
- **Thiên lệch công sức**: Soi đã được chỉnh nhiều tháng trên dữ liệu này (phép kiểm đủ dòng ra đời từ chính phép đo này);
  các phương pháp khác chỉ được cài theo mặc định. Giảm bằng cách: đặt giới hạn công sức như nhau cho bộ chuyển (cùng một
  bộ phân tích số của Soi cho mọi phương pháp: dấu phân cách, ngoặc âm, gạch ngang); chốt cấu hình/prompt của M2–M4 trên
  1 BCTC phát triển (ví dụ PLC Q2/2025), rồi chạy một lần trên 10 BCTC còn lại, không chỉnh sau khi thấy kết quả.
- **Cùng phép kiểm cho mọi phương pháp**: phép kiểm và bộ chấm là code, không phụ thuộc phương pháp đọc; áp nguyên như nhau.
- **Lặp lại**: M4/M5/M6 có ngẫu nhiên; ghi rõ một lần chạy, hoặc chạy M4 hai lần trên 3 BCTC để ước độ dao động (thêm
  ~0,03 USD).
- **Tìm trang và xoay**: cố định cho mọi phương pháp (đo riêng), để không đổ lỗi tìm trang cho bước đọc số.
- **Mô hình cùng nhà**: M4 và M5 cùng Haiku 5.5 — công bằng giữa hai cách đọc, nhưng không nói gì về nhà cung cấp khác; so
  sánh nhà cung cấp đã có riêng (Haiku 99,4% vs gpt-5.4-mini 93,0% ô đọc được lần đầu, ghi chú dự án).

### 4.8 Kết quả mong đợi để viết (giả thuyết, chưa đo)

M1 không áp dụng cho bản scan; M2 giảm mạnh ở 120/72 dpi và hay vỡ cấu trúc ở bảng không kẻ; M3 tốt hơn M2 về cấu trúc
nhưng vẫn mang lỗi chữ số của OCR; M4 sửa được cấu trúc nhưng không sửa được chữ số; M5a cao ở mọi mức trừ 72 dpi; M5b nâng
72 dpi lên. Phần lớn lỗi chữ số của mọi phương pháp bị phép kiểm báo — tức phép kiểm là đóng góp dùng được cho mọi phương
pháp, không chỉ cho VLM. Không viết các câu này vào báo cáo trước khi đo.

---

## 5. Bản thảo thay cho mục "Hệ thống của khóa trước" (LaTeX)

Ghi chú khi dán vào báo cáo:

- Số "Number F1 khoảng 85% trên 401 trang" (85,32% cho Hybrid OCR; Docling với Tesseract 81,56%; Marker 87,80%) và
  "khoảng 5 phút mỗi báo cáo" (301 giây cho FPT quý 3/2024, trong đó OCR 194 giây trên GPU) **có nguồn**: báo cáo IT3940E
  của tác giả (bản lưu ở D:/Project 3/report, trích bằng `prevcohort`). Lần tìm đầu chỉ xem README và mã nguồn công khai
  nên đã ghi nhầm là không có nguồn (sửa 22/10/2026).
- Bảng so sánh giờ là bảng **theo họ phương pháp**, định tính; số đo đặt ở chương kết quả sau khi chạy thí nghiệm (mục mới
  "So sánh các phương pháp đọc trên cùng bộ đáp án"). Trước khi đo, phần kết quả chỉ để đề mục `\chualam` ở "Hướng phát
  triển" (thay đề mục cũ "Mở rộng bộ đáp án và so với khóa trước trên bộ vnpdf").
- Các chỗ khác còn chữ "khóa trước" cần sửa cùng lúc: dòng 274 (đóng góp "đủ các cột": viết "Các hệ thống trích xuất hiện
  có, ví dụ~\cite{prevcohort}, chỉ lưu một giá trị..."), dòng 290 (cấu trúc báo cáo: "Chương 3 điểm lại các phương pháp trích
  xuất số và các sản phẩm liên quan"), dòng 885 ("logic lấy danh sách tài liệu dựa trên mã nguồn mở Stock Report
  Agent~\cite{prevcohort}, giấy phép MIT"), dòng 1773 (so token với "một hệ thống OCR + mô hình văn bản"; số 272.054 token,
  0,04 USD cần nguồn), dòng 2085 (đề mục hướng phát triển).
- Khóa bib `prevcohort` có thể giữ tên khóa; tiêu đề mục bib đã trung tính.

```latex
\section{Các phương pháp trích xuất số từ BCTC}\label{sec:phuongphap}
Bài toán của Soi là lấy ra đúng từng ô số (dòng nào, cột nào, giá trị bao nhiêu) của ba báo cáo chính từ file PDF. Khó
khăn nằm ở dữ liệu: phần lớn BCTC là bản scan, có file độ phân giải thấp hoặc trang bị xoay; số viết theo hai kiểu dấu
phân cách hàng nghìn, số âm để trong ngoặc, dấu gạch nghĩa là không có số; tên chỉ tiêu dài và xuống dòng; bảng có
bốn đến sáu cột số xen với cột mã số và cột thuyết minh. Với bài toán này, sai một chữ ở tên chỉ tiêu ít hại; sai một
chữ số, mất dấu âm hay đặt đúng số vào sai dòng mới làm hỏng số liệu. Có năm họ phương pháp chính.

\subsection{Dùng lớp chữ có sẵn trong file}
Khi công ty xuất BCTC thẳng từ Excel, Word hoặc phần mềm kế toán, file PDF chứa sẵn chữ và vị trí của chữ. Chỉ cần gom
chữ thành hàng theo vị trí dọc và xếp số vào cột theo mép phải là có bảng đúng tuyệt đối, miễn phí và rất nhanh. Nhược
điểm là cách này gần như không dùng được với BCTC Việt Nam: trong 119 BCTC của đề tài chỉ 5 file có chữ gốc; nhiều file
có lớp chữ do máy nhận dạng từ ảnh tạo ra, sai chính tả và tách vỡ số, nên phải đánh giá chất lượng lớp chữ chứ không
chỉ xem có hay không. Soi dùng chính loại file hiếm này làm đáp án để đo độ đúng (mục~\ref{sec:dapan}).

\subsection{Nhận dạng ký tự (OCR) rồi dựng bảng bằng luật}
Phần mềm OCR như Tesseract, PaddleOCR hay VietOCR tìm các dòng chữ trên ảnh và nhận dạng từng dòng, kèm vị trí và điểm
tin cậy. Sau đó luật gom hàng, gom cột dựng lại bảng như với lớp chữ có sẵn. Ưu điểm: miễn phí, chạy trên máy cá nhân,
kết quả lặp lại được, có điểm tin cậy cho từng từ. Nhược điểm trên BCTC scan: dấu tiếng Việt nhỏ nên dễ mất khi ảnh
mờ hoặc nén mạnh; với số thì nhầm dấu chấm và dấu phẩy, mất dấu ngoặc, nhầm các chữ số có nét gần nhau ở ảnh độ phân
giải thấp; luật dựng bảng dễ vỡ khi tên chỉ tiêu xuống dòng, bảng không kẻ ô hoặc trang bị xoay.

\subsection{OCR kết hợp mô hình ngôn ngữ đọc văn bản}
Văn bản OCR được đưa cho một mô hình ngôn ngữ để sắp thành bảng có cấu trúc. Mô hình xử lý tốt phần bố cục: ghép tên
chỉ tiêu bị xuống dòng, nhận ra cột nào là quý này, cột nào là lũy kế. Đọc văn bản cũng rẻ hơn đọc ảnh nhiều lần. Nhưng
mô hình không nhìn thấy ảnh nên không sửa được chữ số mà OCR đã đọc sai, và có thể tự ý \enquote{sửa} số cho hợp lý mà
không ai biết nếu không có phép kiểm. Hệ thống mã nguồn mở Stock Report Agent~\cite{prevcohort} là một ví dụ của cách
làm này: chuyển PDF thành văn bản bằng một bộ chuyển đổi tài liệu với Tesseract tiếng Việt, đọc lại các ô số có độ tin
cậy thấp bằng một mô hình OCR thứ hai (Surya), rồi dùng mô hình ngôn ngữ tách ba báo cáo và đổi đơn vị.
% Nguồn: báo cáo IT3940E của tác giả (prevcohort): Number F1 85,32% trên 401 trang; 301 giây mỗi báo cáo (FPT Q3/2024).
Thước đo mà hệ thống này công bố đếm các số trùng nhau trên cả trang, không xét số nằm ở dòng nào, cột nào, nên chưa cho
biết tỷ lệ ô đúng.

\subsection{Mô hình nhận dạng cấu trúc bảng và bộ chuyển đổi tài liệu}
Các công cụ như Docling, Marker, MinerU dùng một mô hình tìm vùng bảng và một mô hình đoán lưới hàng, cột (ví dụ Table
Transformer~\cite{smock2022pubtables}, TableFormer), sau đó điền chữ do OCR đọc vào từng ô và xuất ra bảng. Ưu điểm là
giữ được cấu trúc bảng tổng quát và chạy trên máy cá nhân. Nhược điểm: các mô hình này chủ yếu được huấn luyện trên bài
báo khoa học và tài liệu tiếng Anh; với bảng không kẻ ô của ngân hàng, cột số hay bị gộp hoặc tách sai, cột mã số và
thuyết minh bị lẫn vào cột số; chất lượng chữ Việt phụ thuộc phần OCR bên dưới; cần GPU để chạy nhanh. Một số công cụ có
giới hạn giấy phép cho trọng số mô hình khi dùng thương mại.

\subsection{Mô hình ngôn ngữ đọc ảnh chép thẳng}
Mô hình đa phương thức nhận ảnh trang và chép từng ô thành dữ liệu có cấu trúc trong một bước, không cần dựng bảng riêng.
Cách này đọc tốt bảng nhiều cột, tên xuống dòng và chữ có dấu, dùng một cách cho mọi mẫu biểu và không cần GPU. Nhược
điểm: không có điểm tin cậy cho từng ô, đôi khi chép lệch dòng hoặc đọc nhầm số, kết quả giữa các lần chạy không giống hệt
nhau, và tốn tiền theo số ảnh gửi đi. Soi theo cách này nhưng giới hạn vai trò của mô hình: mô hình chỉ chép nguyên văn;
code hiểu số, đơn vị, dấu; độ tin cậy đến từ ràng buộc kế toán và từ việc đọc lại đúng các ô bị nghi.

\subsection{Phép kiểm kế toán dùng được cho mọi phương pháp}
Các họ trên khác nhau ở cách đọc, nhưng đầu ra cuối cùng đều là một bảng số, nên phép kiểm kế toán (tổng các khoản bằng
dòng tổng, tài sản bằng nguồn vốn, số đầu năm khớp BCTC kỳ trước) áp được cho tất cả. Vì vậy câu hỏi so sánh gồm hai phần:
mỗi cách đọc đúng bao nhiêu ô, và phép kiểm phát hiện được bao nhiêu phần lỗi của từng cách. Bảng~\ref{tab:phuongphap}
tóm tắt các họ phương pháp.

\begin{table}[H]
\centering\small
\caption{Các họ phương pháp trích xuất số từ BCTC}\label{tab:phuongphap}
\begin{tabularx}{\linewidth}{@{}>{\raggedright\arraybackslash}p{2.6cm}XXp{2.3cm}@{}}
\toprule
\textbf{Phương pháp} & \textbf{Điểm mạnh} & \textbf{Điểm yếu với BCTC scan} & \textbf{Chi phí, phần cứng} \\ \midrule
Lớp chữ có sẵn & Đúng tuyệt đối khi là chữ gốc; rất nhanh & Chỉ 5/119 BCTC có chữ gốc; lớp chữ OCR sẵn thường hỏng
& Miễn phí, CPU \\
OCR + luật dựng bảng & Miễn phí, lặp lại được, có điểm tin cậy & Mất dấu, nhầm chấm/phẩy, mất ngoặc âm; vỡ bảng khi
tên xuống dòng, bảng không kẻ, trang xoay & Miễn phí, CPU \\
OCR + mô hình đọc văn bản & Sửa được bố cục; rẻ hơn đọc ảnh & Không sửa được chữ số OCR đọc sai; có thể tự ý sửa số
& Rẻ; CPU \\
Mô hình cấu trúc bảng, bộ chuyển đổi tài liệu & Giữ cấu trúc bảng tổng quát; chạy cục bộ & Gộp/tách cột sai ở bảng không
kẻ; chữ Việt phụ thuộc OCR; giấy phép trọng số có giới hạn & Miễn phí; nên có GPU \\
Mô hình đọc ảnh chép thẳng (Soi) & Một bước cho mọi mẫu biểu; đọc tốt bảng nhiều cột, chữ có dấu & Không có điểm tin
cậy; đôi khi chép lệch dòng; tốn tiền theo ảnh & Trả theo lượt gọi; không cần GPU \\
\bottomrule
\end{tabularx}
\end{table}
```

Mục bib cần thêm nếu dùng câu Table Transformer:

```bibtex
@inproceedings{smock2022pubtables,
  author    = {Brandon Smock and Rohith Pesala and Robin Abraham},
  title     = {{PubTables-1M}: Towards Comprehensive Table Extraction from Unstructured Documents},
  booktitle = {Proceedings of the IEEE/CVF Conference on Computer Vision and Pattern Recognition (CVPR)},
  year      = {2022}
}
```

Đề mục cho "Hướng phát triển" (thay đề mục cũ), cho tới khi đo xong:

```latex
\subsection{So sánh các phương pháp đọc số trên cùng bộ đáp án chữ gốc}\chualam
```

---

## Nguồn

- Dataset vnpdf: https://huggingface.co/datasets/kiethuynhanh/vnpdf-financial-reports-dataset
- Stock Report Agent (MIT): https://github.com/buinguyenkhai/stock-report-agent-20251 (README; `evaluation/ocr_benchmark/metrics.py`, `page_level_benchmark.py`, `dataset_loader.py`)
- Docling technical report: https://arxiv.org/html/2408.09869v5
- PubTables-1M / Table Transformer: https://arxiv.org/pdf/2110.00061
- OmniDocBench (CVPR 2025): https://arxiv.org/html/2412.07626v2
- Real5-OmniDocBench: https://arxiv.org/pdf/2603.04205
- Bảng xếp hạng OmniDocBench (cộng đồng): https://www.codesota.com/ocr/benchmark/omnidocbench
- PaddleOCR PP-OCRv5 đa ngôn ngữ: https://www.paddleocr.ai/latest/en/version3.x/algorithm/PP-OCRv5/PP-OCRv5_multi_languages.html
- Tổng hợp giấy phép (thứ cấp): https://wikidocs.net/441164
- Marker README (bản sao): https://github.com/sddai/markerPDF ; Marker/MinerU/Docling (blog, thứ cấp): https://particula.tech/blog/docling-vs-mineru-vs-marker-pdf-parser
- Tesseract tiếng Việt: https://vietunicode.sourceforge.net/howto/tesseract-ocr.html
- Khảo sát OCR tiếng Việt: https://www.themoonlight.io/fr/review/a-survey-on-vietnamese-document-analysis-and-recognition-challenges-and-future-directions
- VietOCR (dùng với PaddleOCR): https://viblo.asia/p/deepdoc-vietocr-cong-cu-ocr-cho-tieng-viet-nhanh-va-tiet-kiem-chi-phi-2vJPdGO8JeK , https://github.com/bmd1905/vietnamese-ocr
