# Code

Mã nguồn của dự án. Cấu trúc theo [kiến trúc kỹ thuật](../Baocao/dinh-huong/architecture.md#14-cấu-trúc-repo-đề-xuất).

| Thư mục | Nội dung | Trạng thái |
|---|---|---|
| `infra/` | Docker Compose: PostgreSQL 16 + pgvector | Có |
| `db/migrations/` | Lược đồ CSDL (file `.sql`, áp dụng theo thứ tự tên) | Có |
| `db/seeds/` | Danh sách công ty (VN30) | Có |
| `services/ingestion/` | Thu thập BCTC: lấy danh sách từ Vietstock, nhận dạng tiêu đề, tải file | Có |
| `services/extraction/` | Đọc và kiểm chứng BCTC: chọn PDF, định vị trang, chép bảng bằng mô hình đọc ảnh, chuẩn hóa số, kiểm tra ràng buộc kế toán | Bản đầu; 30/30 BCTC hợp nhất quý 2/2026 của VN30 đạt |
| `services/llm.py` | Gọi mô hình qua giao diện kiểu OpenAI (Gemini, OpenAI, OpenRouter, Ollama) | Có |
| `eval/` | Chấm kết quả trích xuất với bộ duyệt tay (`Data/golden/`) | Có |
| `services/metrics/` | Thẻ KQKD: số chính kèm nguồn tới trang, quy tắc hiển thị tăng trưởng, 7 cờ cảnh báo, % kế hoạch ĐHCĐ | Bản đầu |
| `services/api/` | Web: bảng mùa BCTC, thẻ từng mã, theo dõi, yêu cầu đọc BCTC / tải file lên, hàng duyệt; đăng nhập bằng link email | Bản đầu, chạy trên máy |
| `services/watcher/`, `services/alerts.py`, `services/ondemand.py`, `services/users.py` | Bộ canh, email cho người theo dõi, hàng chờ yêu cầu, người dùng được mời | Bản đầu |
| `services/analyst/`, `services/news/`, `apps/web/`, `eval/` | Phân tích, tin tức, giao diện, đánh giá | Sau |

## Cài đặt

Cần Docker Desktop. Mọi thứ chạy trong container Linux: CSDL, web, bộ canh và các lệnh chạy một lần. Đây cũng là cách
chạy trên VPS. Trên Windows có bật Smart App Control, thư viện kết nối PostgreSQL (`psycopg`) chạy trực tiếp bị chặn.

```bash
cd Code
copy .env.example .env          # Linux/macOS: cp .env.example .env; rồi điền key mô hình
docker compose -f infra/docker-compose.yml up -d --build      # CSDL (cổng 5433), web (http://127.0.0.1:8765), bộ canh
docker compose -f infra/docker-compose.yml run --rm app python -m services.ingestion migrate
docker compose -f infra/docker-compose.yml run --rm app python -m pytest -q
```

Thư mục `Code/` và `Data/raw/` được gắn vào container, nên sửa code có hiệu lực ngay (web cần
`docker compose -f infra/docker-compose.yml restart web`). Các lệnh `python -m ...` dưới đây chạy trong container bằng
`docker compose -f infra/docker-compose.yml run --rm app <lệnh>`. Vẫn có thể chạy trực tiếp bằng venv (Python 3.12,
`pip install -e ".[dev]"`) trên máy không chặn `psycopg`.

## Thu thập BCTC

```bash
python -m services.ingestion migrate                     # tạo/cập nhật bảng
python -m services.ingestion seed                        # ghi danh sách VN30
python -m services.ingestion discover --year 2026        # lấy danh sách BCTC từ Vietstock
python -m services.ingestion report --year 2026 --period Q2 --csv ../Data/bctc_q2_2026_vn30.csv
python -m services.ingestion download --year 2026 --period Q2   # tải file về ../Data/raw/
```

- Các lệnh chạy lại nhiều lần không tạo dữ liệu trùng: tài liệu khóa theo mã tài liệu của nguồn, file khóa theo SHA-256.
- File tải về nằm trong `Data/raw/` (không đưa lên GitHub).
- `--tickers FPT,VCB` để chỉ chạy một số mã; `--delay` để chỉnh thời gian nghỉ giữa các request (mặc định 1 giây).

## Đọc và kiểm chứng BCTC

Cần API key của một nhà cung cấp mô hình trong `.env` (xem `.env.example`).

```bash
python -m services.llm                                            # kiểm tra key, liệt kê mô hình dùng được
python -m services.extraction run --tickers FPT --year 2026 --period Q2 --scope consolidated
python -m services.extraction show --doc-id 28                    # các ràng buộc bị lệch
python -m services.extraction reread --doc-id 28                  # đọc lại các ô thuộc ràng buộc bị lệch
python -m services.extraction recheck --doc-id 28                 # kiểm tra lại từ kết quả đã lưu (khi sửa rules.py), không gọi mô hình
python eval/golden.py                                             # chấm với bộ duyệt tay
python eval/external.py --year 2026 --period Q2                 # đối chiếu thẻ với CafeF, chỉ dùng nội bộ
```

- Mô hình chỉ định vị trang và chép nguyên văn các ô; đổi chuỗi thành số, đổi đơn vị, kiểm tra cộng tổng đều bằng code.
- Ràng buộc kế toán khai báo theo mẫu trong `services/extraction/rules.py`: TT200 đầy đủ; TT99 mới có các dòng tổng;
  ngân hàng (TCTD) và công ty chứng khoán (CTCK, mới có các dòng tổng). Mẫu (TT200/TT99) nhận dạng bằng phép cộng kiểm tra, không suy từ năm.
- Kết quả từng tài liệu lưu ở `Data/raw/extracted/<mã>/<id>_<sha>.json` và trong bảng `line_items`, `validations`.
- Ràng buộc bắt buộc bị lệch thì đọc lại đúng các ô liên quan ở độ phân giải cao hơn, **không** cho mô hình biết
  con số mong đợi (để mô hình không "sửa cho khớp"); mọi lần đọc lại được ghi lại cả giá trị trước và sau.
- Trang in xoay ngang được nhận ra ở bước định vị trang và xoay thẳng trước khi chép bảng.
- Quy ước dấu (chi phí in số dương hay số âm trong ngoặc) được nhận ra theo từng tài liệu.
- Mã số in trùng trên chính BCTC được ghi lại (`duplicate_codes`) thay vì để dòng sau đè dòng trước.
- Ngân hàng (mẫu TCTD) không in mã số: `services/extraction/bank.py` gán mã chuẩn `b.*` theo tên chỉ tiêu (so khớp sau
  khi bỏ dấu, để không phụ thuộc kiểu bỏ dấu cũ/mới như "khóan"/"khoán"), rồi kiểm tra theo bộ ràng buộc TCTD.
  Tên chỉ tiêu viết theo cách gọi thực tế của 8 ngân hàng quý 2/2026; gặp ngân hàng mới có thể cần thêm biến thể.
- Thang leo thang khi lệch: đọc lại ô ở độ phân giải cao hơn, rồi chép lại cả báo cáo theo từng trang.
- Trước khi gọi lại mô hình, code thử các giả thuyết sửa lỗi miễn phí và để ràng buộc kế toán chọn: đảo cột mã số với
  số thứ tự (theo từng trang), sửa tên chỉ tiêu bị lệch dòng (ngân hàng), gán mã cho dòng bị thiếu mã khi số của nó
  khớp đúng phần còn thiếu của một ràng buộc. Mọi chỗ tự sửa được ghi lại và hiện trên web.
- "Đã kiểm chứng" đòi hỏi: không ràng buộc bắt buộc nào lệch, có ràng buộc trên cả BCĐKT và KQKD, và kiểm được
  tổng tài sản = tổng nguồn vốn (thiếu trang nguồn vốn thì chép thêm trang kế tiếp).
- Bằng chứng từng ô (`services/extraction/evidence.py`, không gọi mô hình): ô nằm trong ràng buộc cộng tổng đã đạt,
  và/hoặc khớp với BCTC khác của cùng công ty: số đầu năm giữa các quý, quý = lũy kế kỳ này − lũy kế kỳ trước, quý 2
  với BCTC bán niên (cùng ngày 30/06), quý 4 với BCTC năm. Hai lần đọc độc lập từ hai bộ ảnh khác nhau cùng ra một
  con số là bằng chứng mạnh, và phủ được cả ô không thuộc phép cộng nào.
- Hai BCTC in một con số khác nhau thì hoặc một bên đọc sai, hoặc công ty đã sửa số (bản bán niên được kiểm toán soát
  xét nên hay khác bản quý 2 công ty tự lập). Khi cộng tổng ở cả hai bên đều khớp và chênh lệch không phải dạng sai 1-2
  chữ số, coi là số thật khác nhau. Còn lại là "cần xem lại": `verify` đọc lại riêng từng ô đó ở ảnh nét hơn trên cả
  hai BCTC (`services/extraction/verify.py`). Đọc lại vẫn ra như cũ thì là số thật khác nhau; ra số khác thì chỉ giữ
  số mới khi nó làm hai BCTC khớp nhau và không làm hỏng ràng buộc nào (ô ngoài phép cộng có thể bị đọc nhầm dòng).
  Quý 2/2026: 77 ô cần xem lại, đọc lại 140 ô trên 35 BCTC hết 0,19 USD, sửa 19 lỗi đọc, còn 7 ô.

  ```bash
  python -m services.extraction evidence --year 2026 --period Q2   # độ phủ và các ô cần xem lại của cả kỳ
  python -m services.extraction verify --year 2026 --period Q2     # đọc lại các ô cần xem lại (gọi mô hình)
  python -m services.extraction cost                               # chi phí gọi mô hình theo bước
  ```
- Chi phí: mỗi lần gọi mô hình được ghi theo bước (định vị trang, chép từng báo cáo, chép lại, đọc lại ô) vào
  `usage_by_step` của bản ghi; giá mỗi mô hình ở `services/llm.py` (`PRICES`). Bước chép bảng tốn khoảng 0,05-0,12 USD
  một BCTC, phần lớn là token ra (chính các con số được chép). Thử hạ mức suy luận từ `low` xuống `none` (11/10/2026,
  VCB, SSI, VIC): rẻ hơn khoảng 8% nhưng VIC trượt 4/32 ràng buộc, nên giữ `low`.
- Chưa làm: đọc lại bằng mô hình mạnh hơn.

Kết quả thử với `gpt-5.4-mini` trên BCTC hợp nhất quý 2/2026 (03/10/2026), số ràng buộc bắt buộc đạt:

| Mã | Mẫu nhận dạng | Ràng buộc bắt buộc | Ghi chú |
|---|---|---|---|
| FPT | TT99 | 32/32 | Đọc sai 1 chữ số ở doanh thu thuần quý; ràng buộc khoanh đúng ô, đọc lại sửa đúng (đã đối chiếu ảnh gốc) |
| HPG | TT99 (in mã tổng tài sản 270) | 32/32 | BCTC tự in trùng mã 230 cho tài sản sinh học dài hạn và BĐS đầu tư |
| MWG | TT99 | 34/34 | Trang KQKD in xoay ngang; chi phí in số âm |
| VNM | TT99 | 32/32 | |
| ACB, BID, CTG, LPB, MBB, TCB, VCB, VPB | TCTD | 38–44/38–44 mỗi ngân hàng | Lệch ban đầu chủ yếu do tên chỉ tiêu khác nhau giữa các ngân hàng; LPB có 1 ô đọc sai 10 tỷ ở LCTT, chép lại theo trang thì đúng |

Trung bình khoảng 50 nghìn token vào và 12 nghìn token ra cho mỗi BCTC (khoảng 0,09 USD với giá ngày 03/10/2026).

## Thẻ KQKD và cờ cảnh báo

`services/metrics/card.py` tính bằng code từ số đã kiểm chứng (mô hình ngôn ngữ không tham gia), theo kế hoạch MVP:

- Số chính (DN thường: doanh thu thuần, lợi nhuận gộp, LNST của cổ đông công ty mẹ; ngân hàng: thu nhập lãi thuần, tổng thu
  nhập hoạt động, chi phí dự phòng, LNTT, LNST), quý và lũy kế so với cùng kỳ. Mỗi số mang nguồn: tài liệu, mã số, trang,
  chuỗi nguyên văn.
- Kỳ này hoặc cùng kỳ lỗ thì không in %, viết bằng chữ ("lỗ thu hẹp từ X còn Y", "chuyển từ lỗ X sang lãi Y").
- 7 cờ: lỗ hoặc đổi dấu; tăng trưởng do nền thấp (cần LNST ít nhất 2 trong 4 quý trước quý cùng kỳ); lợi nhuận phần lớn
  ngoài hoạt động chính; hoàn nhập dự phòng; mua bán công ty con hoặc biến động lớn ở công ty liên kết; có lãi nhưng dòng
  tiền kinh doanh âm; số liệu bị sửa giữa các BCTC (dùng đối chiếu ở `evidence.py`). Khoản nhỏ hơn ngưỡng (5% LNTT,
  hoặc chênh dưới 0,5% và dưới 1 tỷ) không gắn cờ.
- % kế hoạch năm: kế hoạch ĐHCĐ nhập tay vào `db/seeds/agm_plans_2026.csv` (cột `value_ty` tính bằng tỷ đồng, bắt buộc
  có link nghị quyết), nạp bằng `python -m services.metrics plans`.
- Công ty chứng khoán, bảo hiểm: chưa có thẻ.

```bash
python -m services.metrics card --ticker FPT --year 2026 --period Q2
```

## Web

```bash
python -m services.users invite ban@example.com [--admin]   # chỉ người được mời mới đăng nhập được
python -m services.api --port 8765                          # rồi mở http://127.0.0.1:8765
```

- Đăng nhập bằng link gửi qua email (không mật khẩu). Chưa cấu hình SMTP mà đang chạy trên chính máy đó thì link hiện
  ngay trên trang. Token chỉ lưu dạng mã băm.
- `/mua-bctc/q2-2026`: các mã VN30, LNST quý và cờ. `/ma/FPT?ky=q2-2026`: thẻ KQKD, bấm vào số để mở trang BCTC gốc.
  Bảng mùa xếp hạng theo tăng trưởng LNST (lãi tăng/giảm, chuyển lỗ sang lãi... không in % khi có kỳ lỗ), lọc theo cờ,
  cờ "số bị sửa" và loại công ty.
- `/lich` (mặc định mùa đang diễn ra) hoặc `/lich/q3-2026`: mã nào đã công bố, ngày dự kiến theo thói quen các quý
  trước, hạn 20 hoặc 30 ngày, quá hạn chưa công bố.
- `/chia-se/FPT/q2-2026` và `/anh/FPT/q2-2026.png`: trang và ảnh thẻ 1200x630 để chia sẻ, công khai (không cần đăng
  nhập), chỉ cho thẻ đã kiểm chứng hoặc duyệt tay. Ảnh vẽ bằng pymupdf với phông DejaVu (cài trong image Docker).
  `/api/the/FPT?ky=q2-2026`: thẻ dạng JSON. BCTC chỉ được xuất bản khi đã kiểm chứng hoặc đã duyệt tay.
- `/theo-doi`: danh sách theo dõi. Bộ canh gửi một email cho mỗi BCTC của mã đang theo dõi khi thẻ được xuất bản.
- `/yeu-cau`: đọc BCTC quý của mã ngoài VN30, hoặc tải file lên. Một kho chung: BCTC đã đọc thì trả ngay. File tải lên
  nhận diện bằng mã băm SHA-256; có bản chính thức trên Vietstock thì dùng bản đó, không có thì đọc file tải lên và chỉ
  người tải lên xem được. Mỗi người `daily_quota` yêu cầu mới mỗi ngày (mặc định 3); tổng chi phí mô hình mỗi tháng
  không vượt `LLM_MONTHLY_BUDGET_USD` (mặc định 20). Bộ canh xử lý hàng chờ mỗi lượt.
- Người duyệt (`--admin`): `/duyet` liệt kê BCTC chưa đạt kiểm chứng; trang `/tai-lieu/{id}` đặt số cạnh ảnh gốc, cho
  sửa từng ô (ghi lại người sửa, số cũ, số mới) rồi xuất bản. `/noi-bo`: mọi BCTC đã đọc và độ phủ bằng chứng.

## Kiểm thử

```bash
python -m pytest                                 # toàn bộ
python -m pytest tests/test_titles.py -k parse   # một nhóm test
```

## Ghi chú về dữ liệu

- `source_listed_at` là thời điểm Vietstock đăng hoặc cập nhật tài liệu, **không phải** thời điểm công bố chính thức. Nhiều ngân hàng có cùng một mốc giờ (ví dụ BID, MBB, SSB, STB cùng 31/07/2026 11:35), cho thấy đây là giờ Vietstock tải lên hàng loạt. Thời điểm công bố chính thức (`published_at`) sẽ lấy từ HOSE/HNX hoặc cổng CBTT của UBCKNN.
- Một số tài liệu là file `.zip` (quý 2/2026: 5/58 file, của SSI, TCX, VPB), cần giải nén ở bước trích xuất.
- Logic gọi danh sách tài liệu Vietstock dựa trên repo khóa trước [stock-report-agent-20251](https://github.com/buinguyenkhai/stock-report-agent-20251) (giấy phép MIT).
