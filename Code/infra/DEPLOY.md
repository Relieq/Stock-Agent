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

## 5. Cập nhật mã

```bash
git pull && docker compose -f infra/docker-compose.yml -f infra/docker-compose.prod.yml up -d --build
docker compose -f infra/docker-compose.yml -f infra/docker-compose.prod.yml run --rm app python -m services.ingestion migrate
```

Không chạy migration sửa bảng `documents` khi bộ canh đang đọc BCTC (khóa chéo); dừng bộ canh trước.
