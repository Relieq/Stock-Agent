#!/bin/sh
# Sao lưu hằng ngày (dịch vụ backup trong docker-compose.yml): CSDL (pg_dump) và các file không tải lại được trong
# Data/raw (bản ghi trích xuất gồm ô sửa tay và mọi kết quả mô hình đã trả tiền, cài đặt trang quản trị, file người
# dùng tải lên). PDF tải từ Vietstock không sao lưu vì tải lại được. Giữ KEEP bản gần nhất.
#
# Khôi phục CSDL: gunzip -c soi-db-<ngày>.sql.gz | docker exec -i soi-db psql -U soi -d soi
set -eu
KEEP=${KEEP:-14}
while true; do
  stamp=$(date +%Y%m%d-%H%M)
  pg_dump -h db -U soi -d soi | gzip > "/backup/soi-db-$stamp.sql.gz.part"
  mv "/backup/soi-db-$stamp.sql.gz.part" "/backup/soi-db-$stamp.sql.gz"
  (cd /data && tar -czf "/backup/soi-data-$stamp.tar.gz.part" $(ls -d extracted settings.json uploads second_read 2>/dev/null))
  mv "/backup/soi-data-$stamp.tar.gz.part" "/backup/soi-data-$stamp.tar.gz"
  for kind in db data; do
    ls -1t /backup/soi-$kind-* 2>/dev/null | tail -n +$((KEEP + 1)) | xargs -r rm -f
  done
  echo "[$stamp] đã sao lưu vào /backup"
  sleep 86400
done
