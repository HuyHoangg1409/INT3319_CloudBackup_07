# Biên bản nghiệm thu hệ thống CloudBackup — Nhóm 7

- **Ngày giờ lập biên bản:** 2026-11-15 07:45 UTC (14:45 GMT+7)
- **Phiên bản mã nguồn:** Triển khai tại `/opt/cloudbackup` (cập nhật cuối `2026-11-12`); đã đối chiếu khớp mã băm SHA-256 các tệp nguồn/cấu hình và xuất `requirements.lock.txt` từ `.venv` thực tế trên EC2.
- **OS:** Amazon Linux 2023 | **PostgreSQL:** 15.19 | **Python:** 3.9.25 (`boto3==1.42.97`, `botocore==1.42.97`)
- **Region:** ap-southeast-1 | **Bucket:** `cloud-backup-07-unique` | **Instance:** `i-09e3d76a3f2db386b` (`t3.micro`)
- **Người thực hiện & kiểm thử:** Hoàng (phụ trách chính / Backup & tích hợp), Dương (Restore & kiểm thử), Hưng (CloudWatch & SNS), Đức (Cron, heartbeat & tài liệu)

> **Quy ước ghi nhận:** Không ghi secret, private key hoặc access key. Trạng thái hợp lệ: `CHUA_CHAY`, `PASS`, `FAIL`, `BLOCKED`. Phân biệt rõ mục đã xác minh trực tiếp qua file JSON/EC2 với mục ghi nhận từ báo cáo kiểm thử nội bộ.

---

## 1. Bảng kết quả kiểm thử chức năng (T01 – T13)

| Mã | Bài kiểm thử | Trạng thái | Kết quả thực tế và minh chứng |
| :--- | :--- | :--- | :--- |
| **T01** | Backup thành công đủ 4 object | `PASS` | Xác minh `manifest.json` phiên `20261113T132001Z-28f9f17f` (`database.dump` 3.909 bytes, SHA-256 `753b771a...`, `app.conf` 120 bytes) và phiên hồi phục `20261114T061904Z-7e28e417` (`database.dump` 3.908 bytes). S3 lưu đủ 4 object (`database.dump`, `configuration.tar.gz`, `manifest.json`, `SUCCESS.json`) — xem `evidence/T01_s3_objects.png`. |
| **T02** | Restore DB/config đúng baseline | `PASS` | Xác minh trực tiếp 3 file `result.json` trong `evidence/restore-results/` của phiên `20261113T132001Z-28f9f17f`: đều đạt `"status": "RESTORE_PASS"`, khôi phục vào DB riêng (`cloud_restore_201f5412e4494753`, `cloud_restore_0389600f15ea4dfd`, `cloud_restore_ed9afc0630714d35`) và thư mục cấu hình tách biệt; khớp baseline 100 dòng bảng `demo_inventory`, 3 constraint và sequence `last_value=100`. |
| **T03** | Restore chọn phiên A sau khi đã tạo B | `PASS` | Xác minh qua `manifest.json` và `result.json`: Phiên A `20261113T140400Z-2f860ede` (`item_id=1, quantity=3`, `app.conf` SHA-256 `0dd3d172...`) khôi phục `RESTORE_PASS` vào DB `cloud_restore_f1c681de9c464335` (`0.488s`); Phiên B `20261113T141318Z-d4d38046` (`item_id=1, quantity=999`, `app.conf` SHA-256 `d082d8d1...`) khôi phục `RESTORE_PASS` vào DB `cloud_restore_362c9af833b74025` (`0.537s`). |
| **T04** | DB sai, exit 1, state giữ nguyên, SNS | `PASS` | Phiên lỗi `20261113T173407Z-80cd5396` xác nhận không tạo `manifest.json` (`NO_MANIFEST`) trên EC2. Tiến trình trả về exit code 1, `last_success.json` không bị ghi đè, lệnh SNS Publish thành công (báo cáo kiểm thử của Dương). |
| **T05** | S3 denied, không SUCCESS, SNS | `PASS` | Phiên lỗi `20261113T172140Z-1a0e2271` có `manifest.json` cục bộ (`2026-11-13T17:21:40+00:00`) nhưng không ghi object/SUCCESS lên S3, trả về exit code 1 và SNS Publish thành công (báo cáo kiểm thử của Dương). |
| **T06** | Dump đổi một byte, restore từ chối | `PASS` | Xác minh trực tiếp file `20261113T155522Z-68b5bc70-ab9683b2/result.json`: `"status": "FAILED"`, `"database": null`, `"error": "Checksum or size mismatch: database.dump"` (từ chối trước khi tạo DB đích). |
| **T07** | Thiếu SUCCESS, restore từ chối | `PASS` | Xác minh trực tiếp file `20261113T145045Z-8a63539c-405c2727/result.json`: `"status": "FAILED"`, `"database": null`, `"error": "An error occurred (NoSuchKey) when calling the GetObject operation: The specified key does not exist."` (từ chối trước khi tạo DB đích). |
| **T08** | Hai phiên backup từ cron | `PASS` | Xác minh cấu hình `/etc/cron.d/cloudbackup-backup` (`*/5 * * * *`) và `manifest.json` cục bộ của 2 phiên cron liên tiếp: `20261113T171001Z-5dc30dd6` (`17:10:01Z`) và `20261113T171502Z-6f1b0949` (`17:15:02Z`), kèm nhật ký `/var/log/cloudbackup-cron.log` hoạt động liên tục đến `2026-11-15`. |
| **T09a** | Giữ khóa, lần thứ hai exit 75 | `PASS` | Khi chạy chồng tác vụ, tiến trình thứ hai trả về exit code 75 (`SKIPPED_LOCK`); sau khi tiến trình đầu nhả khóa, chạy lại thành công (báo cáo kiểm thử của Dương). |
| **T09b** | Linux timeout test đạt | `PASS` | Bộ kiểm thử đơn vị `tests/test_lab.py` đạt `18/18 PASS`, bao gồm ca kiểm thử `test_real_timeout` (báo cáo kiểm thử của Dương). |
| **T10** | Tắt cron backup, heartbeat còn chạy, alarm | `PASS` | Ngày 14/11/2026: tắt riêng cron backup, giữ cron heartbeat (`* * * * *`), alarm `cloudbackup-nhom7-age` (ngưỡng 900s) chuyển `ALARM` lúc `05:43:22Z`, hồi phục `OK` lúc `05:49:22Z`; SNS action ghi nhận thành công — xem `evidence/T10_T11_alarm_graph.png`. |
| **T11** | Stop EC2, missing metric gây alarm | `PASS` | Ngày 14/11/2026: Stop EC2 lúc `2026-11-14T05:58:37Z`, alarm chuyển `ALARM` do missing data lúc `06:06:46Z` (độ trễ phát hiện 8 phút 09 giây); SNS action ghi nhận thành công — xem `evidence/T10_T11_alarm_graph.png`. |
| **T12** | Hồi phục, backup tốt, alarm OK | `PASS` | Xác minh `manifest.json` của phiên backup hồi phục `20261114T061904Z-7e28e417` (`started_at: 2026-11-14T06:19:04+00:00`), alarm hồi phục `OK` lúc `06:21:46Z`; kiểm tra ngày 15/11/2026 xác nhận cron backup, heartbeat và `last_success.json` (`07:40Z`) hoạt động bình thường. |
| **T13a** | Log trên CloudWatch đúng run_id | `PASS` | CloudWatch Logs (`/cloudbackup/nhom7`) ghi nhận đầy đủ nhật ký JSON theo `run_id` và trạng thái `BACKUP_SUCCESS` — xem `evidence/T13a_cloudwatch_logs.png`. |
| **T13b** | SMS từ lỗi backup đến thật | `BLOCKED` | Luồng Python gọi `sns:Publish` thành công, nhưng gửi SMS thực tế bị chặn ở cấp tài khoản AWS với lỗi: `UserError: The AWS Access Key Id needs a subscription for the service (Service: PinpointSmsVoiceV2, Status Code: 400, Request ID: 89ee8b76-427d-42bb-9050-58c3562797c2)` — xem `evidence/T13b_T13c_sns_sms_blocked.png`. Kênh Email thay thế trên SNS hoạt động bình thường (`evidence/T13_sns_email_received.png`). |
| **T13c** | SMS từ CloudWatch Alarm đến thật | `BLOCKED` | CloudWatch Alarm History đã thực thi SNS Action thành công khi chuyển trạng thái `ALARM`/`OK`, nhưng gửi SMS thực tế bị chặn cùng lỗi tài khoản `PinpointSmsVoiceV2` (Status Code 400, Request ID `89ee8b76-427d-42bb-9050-58c3562797c2`). |

---

## 2. Kết quả đo khôi phục trong môi trường lab (RTO thử nghiệm)

Đo trên cùng máy chủ EC2 `i-09e3d76a3f2db386b` (`t3.micro`) với phiên backup `20261113T132001Z-28f9f17f`:

| Lần | RUN_ID (và mã thư mục restore) | Dòng dữ liệu | Dump bytes | Seconds trong `result.json` | Kết luận |
| :---: | :--- | :---: | :---: | :---: | :--- |
| 1 | `20261113T132001Z-28f9f17f` (`...-ce61244f`, `13:26:09Z`) | 100 | 3.909 | `0.534` | `RESTORE_PASS` (`cloud_restore_201f5412e4494753`) |
| 2 | `20261113T132001Z-28f9f17f` (`...-94773ec1`, `13:47:06Z`) | 100 | 3.909 | `0.505` | `RESTORE_PASS` (`cloud_restore_0389600f15ea4dfd`) |
| 3 | `20261113T132001Z-28f9f17f` (`...-d55e62bd`, `13:52:11Z`) | 100 | 3.909 | `0.538` | `RESTORE_PASS` (`cloud_restore_ed9afc0630714d35`) |

- **Trung bình 3 lần đo:** **0,526 giây** (khoảng dao động: `0,505 – 0,538` giây).
- **Phạm vi kết luận:** Đây là thời gian khôi phục logic cho một cơ sở dữ liệu mẫu (`100` bản ghi) và thư mục cấu hình giả lập trong môi trường lab trên cùng EC2; không đại diện cho RTO toàn bộ hạ tầng sản xuất hay phục hồi khi mất hoàn toàn máy chủ (không phải PITR).

---

## 3. Độ trễ cảnh báo (Ngày 14/11/2026, giờ UTC)

| Tình huống | Metric tốt cuối / Sự kiện gốc | ALARM lúc | Email lúc | SMS lúc | Ghi chú |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Tắt cron backup** | Tắt cron backup, giữ heartbeat mỗi phút | `2026-11-14T05:43:22Z` | Đã xác minh nhận qua SNS (`evidence/T13_sns_email_received.png`) | `BLOCKED` | Hồi phục `OK` lúc `05:49:22Z` sau khi bật lại cron. |
| **Stop EC2** | Stop instance lúc `2026-11-14T05:58:37Z` | `2026-11-14T06:06:46Z` | Đã xác minh nhận qua SNS (`evidence/T13_sns_email_received.png`) | `BLOCKED` | Độ trễ phát hiện missing data: **8 phút 09 giây**; hồi phục `OK` lúc `06:21:46Z`. |

---

## 4. Lỗi còn lại, giới hạn và kế hoạch sau demo

- **Lỗi/Hạn chế đã xác minh:**
  - **Mô tả:** Không nhận được tin nhắn SMS thực tế về điện thoại khi đăng ký/gửi qua Amazon SNS.
  - **Nguyên nhân đã xác minh:** Tài khoản AWS của nhóm chưa được mở gói dịch vụ **AWS End User Messaging SMS (`PinpointSmsVoiceV2`)**, trả về lỗi `UserError: The AWS Access Key Id needs a subscription for the service (Status Code: 400, Request ID: 89ee8b76-427d-42bb-9050-58c3562797c2)`. Ngoài ra, các tệp snapshot tạm từng lưu ở `/tmp/cloudbackup-*` trên EC2 không còn sau chu kỳ Stop/Start EC2; nhóm sử dụng trực tiếp `manifest.json` và `result.json` lưu bền vững tại `/var/backups/cloudbackup/` làm bằng chứng.
  - **Phương án khắc phục:** Lưu ảnh chụp lỗi AWS Console làm bằng chứng khách quan (`evidence/T13b_T13c_sns_sms_blocked.png`), đồng thời kích hoạt kênh Email trên cùng SNS Topic để chứng minh luồng phát thông báo.
- **Trạng thái dữ liệu & lịch vận hành sau demo:**
  - **Dữ liệu nguồn hiện tại:** Đang ở trạng thái B (`item_id=1, quantity=999`, `app.conf` v2); các bản backup và DB restore kiểm thử được giữ nguyên phục vụ chấm bài/bảo vệ.
  - **Lịch sau demo & ngưỡng alarm:** Hiện giữ lịch demo backup 5 phút/lần, heartbeat 1 phút/lần và ngưỡng alarm `cloudbackup-nhom7-age` = `900` giây. Sau khi hoàn tất demo với giảng viên, nhóm sẽ chuyển về lịch hằng ngày (`01:00 GMT+7` tức `18:00 UTC`) đồng bộ với ngưỡng alarm `93600` giây (26 giờ) hoặc Stop EC2 để tránh phát sinh chi phí.

---

## 5. Đối chiếu toàn vẹn mã nguồn & Điều kiện đóng gói

- [x] `README.md` đầy đủ hướng dẫn cài đặt, cấu hình, chạy thủ công, cron, restore và kiểm thử.
- [x] `requirements.lock.txt` đã xuất trực tiếp từ `/opt/cloudbackup/.venv/bin/pip freeze` trên EC2:
  `boto3==1.42.97`, `botocore==1.42.97`, `jmespath==1.1.0`, `python-dateutil==2.9.0.post0`, `s3transfer==0.16.1`, `six==1.17.0`, `urllib3==1.26.20`.
- [x] Mã băm SHA-256 các tệp mã nguồn chính trên EC2 (`/opt/cloudbackup`):
  - `src/backup.py`: `ce77808b7bff2ff3ded44df3d3a75ef4774aa1d21db4460f3a900cbff1de7b1d`
  - `src/common.py`: `eb4bdd622e38a99e1399db1e9000de936af7307a538e56e559172a7dd52dbdbb`
  - `src/heartbeat.py`: `153ec10f3d5ffc8e634fa6d6354b89a0303470cb810721be03f3e65f6f3e54bc`
  - `src/list_backups.py`: `9487473cd6076fdb6e4180e3504308138d4db24cffd297758e9acd2d6053675a`
  - `src/restore_test.py`: `cad32ea74d4927a945f4cfd603756cdacc9e384b06c20317ef73f50042974384`
  - `tests/test_lab.py`: `f349711f28ff9b1d90932b79f3b8055c03ac2a472da571720d30dba328666cab`
- [x] Đã lưu bộ 5 file `result.json` đạt chuẩn trong `evidence/restore-results/` và các ảnh chụp minh chứng tại `evidence/`.
- [x] Bảo đảm gói nộp không chứa tệp `.pem`, AWS credential, mật khẩu hay dữ liệu thật.