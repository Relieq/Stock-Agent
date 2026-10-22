-- Xóa tài khoản thử (@soi.test) cùng báo cáo, yêu cầu, phiên đăng nhập, danh sách theo dõi của chúng trước khi mở cho
-- người dùng thật (xem infra/DEPLOY.md). Chạy MỘT lần, sau khi đã sao lưu:
--   docker exec -i soi-db psql -U soi -d soi -v ON_ERROR_STOP=1 < infra/cleanup_test_data.sql
-- Dừng (không xóa gì) nếu tài khoản thử còn sở hữu file tải lên riêng hoặc từng duyệt tay BCTC.
BEGIN;

DO $$
DECLARE n_owned int; n_reviewed int;
BEGIN
  SELECT count(*) INTO n_owned FROM documents d JOIN users u ON u.id = d.owner_user_id WHERE u.email LIKE '%@soi.test';
  SELECT count(*) INTO n_reviewed FROM documents d JOIN users u ON u.id = d.reviewed_by WHERE u.email LIKE '%@soi.test';
  IF n_owned > 0 OR n_reviewed > 0 THEN
    RAISE EXCEPTION 'Tài khoản thử còn % file tải lên và % BCTC đã duyệt: xử lý tay trước', n_owned, n_reviewed;
  END IF;
END $$;

-- Báo cáo, yêu cầu đọc, phiên, token, theo dõi, thông báo xóa theo (ON DELETE CASCADE)
SELECT email, (SELECT count(*) FROM reports r WHERE r.user_id = u.id) AS reports FROM users u WHERE email LIKE '%@soi.test';
DELETE FROM users WHERE email LIKE '%@soi.test';

COMMIT;
