# Trạng thái kiểm chứng bộ mã

## 1. Kiểm thử đơn vị offline trên Windows (06/11/2026)

Lệnh chạy:

```bash
python -m unittest discover -s tests -v
```

- **Kết quả:** 18 test được phát hiện; **16 PASS**; **2 SKIP** (`test_real_lock_contention` và `test_real_timeout` do yêu cầu Linux `flock` và process groups).
- Các ca mô phỏng kiểm tra commit marker (`SUCCESS.json`), lỗi upload S3, cập nhật `last_success.json`, checksum hỏng, manifest bị sửa đổi, phiên thiếu marker, khôi phục phiên cũ, chế độ `--verify-only`, phân trang S3 và chống tấn công đường dẫn `tar` traversal/symlink.

## 2. Kiểm thử trên EC2 Amazon Linux 2023 & Nghiệm thu (15/11/2026)

- **Kiểm thử đơn vị trên Linux (`tests/test_lab.py`):** Chạy trực tiếp trên instance `i-09e3d76a3f2db386b` (Amazon Linux 2023, Python 3.9.25) đạt **18/18 PASS**, bao gồm cả 2 ca phụ thuộc hệ điều hành Linux (`test_real_lock_contention` và `test_real_timeout`).
- **Kiểm thử tích hợp & nghiệm thu thực tế (T01 – T13):** Đã thực hiện với PostgreSQL 15.19 (`cloud_backup_demo`), Amazon S3 (`cloud-backup-07-unique`), IAM Instance Profile, `cron`, CloudWatch Logs/Metrics/Alarms và Amazon SNS.
- Toàn bộ kết quả đối chiếu và minh chứng được tổng hợp tại [`docs/Nghiem_thu.md`](docs/Nghiem_thu.md) và thư mục [`evidence/`](evidence/).
