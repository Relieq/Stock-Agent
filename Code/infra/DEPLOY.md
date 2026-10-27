# Đưa Soi lên máy chủ

Cấu hình: `docker-compose.yml` (dùng chung) chồng thêm `docker-compose.prod.yml` (mật khẩu CSDL riêng, không mở cổng
CSDL, HTTPS qua Caddy, không hiện link đăng nhập trên trang).

## 1. Chuẩn bị (người quản trị tự làm)

- Máy chủ Linux (Ubuntu 22.04/24.04), 2 vCPU, 4 GB RAM, 40 GB đĩa là đủ cho VN30 (dữ liệu hiện khoảng 2,5 GB, mỗi mùa
  thêm khoảng 0,5 GB PDF).
- Tên miền, bản ghi DNS loại A trỏ về IP máy chủ. Mở cổng 80 và 443.
- Cài Docker Engine và plugin compose theo hướng dẫn chính thức của Docker.

## 2. Mã nguồn và cấu hình

```bash
git clone https://github.com/Relieq/Stock-Agent.git && cd Stock-Agent/Code
```

- `Code/.env`: chép từ máy phát triển (khóa mô hình, SMTP, ADMIN_EMAIL). Thêm `SITE_URL=https://<tên miền>` để link
  trong email và cookie đăng nhập dùng HTTPS. Không đưa file này lên git.
- `Code/infra/.env` (biến cho compose): `DB_PASSWORD=<mật khẩu dài, ngẫu nhiên>`, `SITE_DOMAIN=<tên miền>`,
  `SOI_BACKUP_DIR=/srv/soi-backup`.

## 3. Dữ liệu

Chép từ máy phát triển sang `Stock-Agent/Data/raw/` (khoảng 2,4 GB): `vietstock/`, `hose/` (PDF, cần để hiện ảnh trang
gốc), `extracted/` (kết quả đọc, gồm ô sửa tay), `explanations/`, `second_read/`, `uploads/`, `settings.json`,
`hose_ids.json`, `llm_calls.jsonl` và `llm_cost_baseline.json` (sổ chi phí). Không cần `born_digital/`, `trial/`, `tmp/`.

CSDL: lấy bản sao lưu mới nhất `soi-db-<ngày>.sql.gz` trong `Data/backup` của máy phát triển, rồi trên máy chủ:

```bash
docker compose -f infra/docker-compose.yml -f infra/docker-compose.prod.yml up -d db
gunzip -c soi-db-<ngày>.sql.gz | docker exec -i soi-db psql -U soi -d soi
docker compose -f infra/docker-compose.yml -f infra/docker-compose.prod.yml run --rm app python -m services.ingestion migrate
```

Trước khi mở cho người dùng: xóa tài khoản thử (`@soi.test`) và báo cáo thử của chúng:

```bash
docker exec -i soi-db psql -U soi -d soi -v ON_ERROR_STOP=1 < infra/cleanup_test_data.sql
```

## 4. Chạy

```bash
docker compose -f infra/docker-compose.yml -f infra/docker-compose.prod.yml up -d --build
docker compose -f infra/docker-compose.yml -f infra/docker-compose.prod.yml logs -f caddy web
```

Kiểm tra: mở `https://<tên miền>`, đăng nhập bằng email quản trị (link gửi qua email), xem trang Mùa BCTC, một thẻ,
trang Chi phí. Chỉ một nơi được chạy bộ canh: tắt bộ canh trên máy phát triển
(`docker compose -f infra/docker-compose.yml stop watcher`) để hai nơi không cùng đọc và cùng gửi email.

Theo dõi từ bên ngoài: khi máy chủ hoặc Docker dừng thì hệ thống không tự gửi email được. Tạo một monitor HTTP (ví dụ
UptimeRobot, gói miễn phí, 5 phút một lần) gọi `https://<tên miền>/suc-khoe`, báo email khi mã trả về khác 200. Trang
trả 503 khi bộ canh im quá 120 phút, và lỗi khi web hoặc CSDL hỏng.

## Chạy trên PC ở nhà qua Cloudflare Tunnel (cách đang dùng từ 26/10/2026)

Thay cho mục 1–4 khi không thuê máy chủ: Soi chạy trên PC của người quản trị, web ra ngoài tại `https://soi.rediov.com`
qua Cloudflare Tunnel. Không mở cổng nào trên router, không lộ IP nhà, Cloudflare lo HTTPS (không cần Caddy).

1. Tên miền `rediov.com` dùng DNS của Cloudflare (gói Free). Trong Networking → Tunnels có tunnel `soi`,
   route loại Published application `soi.rediov.com` → `http://web:8765` (tên dịch vụ trong mạng Docker, không phải
   localhost). Các bản ghi khác của tên miền (`maclinh` → GitHub Pages, `www` → Google, email Zoho) để DNS only.
2. Token của tunnel: người quản trị tự dán vào `Code/infra/.env` dòng `CLOUDFLARE_TUNNEL_TOKEN=...` (không đưa lên git).
3. Chạy:

```bash
docker compose -f infra/docker-compose.yml -f infra/docker-compose.home.yml up -d
docker logs soi-cloudflared --tail 20     # phải thấy "Registered tunnel connection"
```

Máy tắt ban đêm: BCTC thường công bố trong giờ làm việc; khi máy bật lại, bộ canh tự quét bù. Docker Desktop cần bật
"Start Docker Desktop when you sign in", và chỉ chạy sau khi đăng nhập Windows. Dịch vụ theo dõi bên ngoài gọi
`/suc-khoe` nên chỉ kiểm trong giờ máy bật, tránh báo lỗi mỗi đêm.

## 5. Cập nhật mã

```bash
git pull && docker compose -f infra/docker-compose.yml -f infra/docker-compose.prod.yml up -d --build
docker compose -f infra/docker-compose.yml -f infra/docker-compose.prod.yml run --rm app python -m services.ingestion migrate
```

Không chạy migration sửa bảng `documents` khi bộ canh đang đọc BCTC (khóa chéo); dừng bộ canh trước.
