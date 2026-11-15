# Hướng dẫn phần Dương
Restore đối chiếu dữ liệu và kiểm thử hệ thống

## 1 Đầu vào và kết quả cần bàn giao
Bạn nhận từ Hoàng một RUN_ID thành công, config ở /etc/cloudbackup.json và bộ mã /opt/cloudbackup. Có thể làm ngay sau backup đầu tiên, không chờ cron hay SMS. Trách nhiệm là chứng minh bản trên S3 dùng được và các lỗi quan trọng bị phát hiện.

Script restore chỉ tạo DB tên cloud_restore_ cộng chuỗi ngẫu nhiên và thư mục recovered mới. Không nhận tham số ghi đè DB nguồn. Khi lỗi, giữ DB test và staging để điều tra, không tự drop database. Điều này giúp tránh mất dữ liệu nhưng bạn cần theo dõi dung lượng khi chạy nhiều lần.

Trên terminal EC2:

```bash
sudo /opt/cloudbackup/.venv/bin/python /opt/cloudbackup/src/list_backups.py
```

Chọn một dòng SUCCESS_MARKER; thay ID trong lệnh dưới bằng RUN_ID thật vừa chọn:

```bash
sudo /opt/cloudbackup/.venv/bin/python /opt/cloudbackup/src/restore_test.py --run-id ID_CUA_PHIEN
echo "RESTORE_EXIT=$?"
```

Kỳ vọng exit 0, RESTORE_PASS và ba dòng: RESULT=..., RESTORE_DB=cloud_restore_..., RESTORED_CONFIG=.... Ghi đủ các giá trị này vào bảng test. Nếu chỉ chạy --verify-only, đó là kiểm tra file/config, không phải đã khôi phục PostgreSQL.

Quy trình tự động: tải SUCCESS và manifest, kiểm tra checksum manifest, tải hai tệp dữ liệu, đối chiếu size/SHA-256, kiểm tra tar an toàn, so sánh từng file config, tạo DB mới, pg_restore và so sánh baseline demo. Sai checksum phải dừng trước khi tạo DB.

Baseline gồm toàn bộ dòng của demo_inventory, thông tin cột, constraint và trạng thái sequence. Đối chiếu tự động hiện chỉ dành cho bảng demo_inventory do bộ seed tạo. Không dùng kết quả này để khẳng định mọi bảng của DB khác đã được kiểm chứng.

---PAGE---
## 2 Kiểm tra thủ công sau restore
Gán tên DB và đường dẫn in ra ở bước trước. Không lấy tên ví dụ nếu trên terminal đang hiển thị tên khác:

```bash
RESTORE_DB='cloud_restore_TEN_THAT'
RESTORED_CONFIG='/var/backups/cloudbackup/restore/THU_MUC_THAT/recovered/config'
sudo -u postgres psql -X -d "$RESTORE_DB" -c '\dt'
sudo -u postgres psql -X -d "$RESTORE_DB" -c 'SELECT COUNT(*) FROM demo_inventory;'
sudo -u postgres psql -X -d "$RESTORE_DB" -c 'SELECT * FROM demo_inventory ORDER BY item_id LIMIT 5;'
sudo cat "$RESTORED_CONFIG/app.conf"
sudo cat "$RESTORED_CONFIG/services/worker.conf"
sudo -u postgres psql -X -d cloud_backup_demo -c 'SELECT COUNT(*) FROM demo_inventory;'
```

Kỳ vọng cả DB gốc và DB restore có 100 dòng ban đầu; config có version=1. Kiểm tra thêm constraint và sequence bằng lệnh sau:

```bash
sudo -u postgres psql -X -d "$RESTORE_DB" -c '\d demo_inventory'
sudo -u postgres psql -X -d "$RESTORE_DB" -c 'SELECT last_value,is_called FROM demo_inventory_item_id_seq;'
```

Lưu result.json từ đường dẫn RESULT. Không chỉ chụp màn hình “pg_restore không báo lỗi”; cần có truy vấn và so sánh dữ liệu/config. Không gọi pg_restore --clean vào cloud_backup_demo.

## 3 Đo thời gian khôi phục
Chạy restore cùng một phiên ít nhất 3 lần; mỗi lần tạo DB và staging mới. result.json có seconds tính cả download, checksum, config, restore và đối chiếu. Ghi thêm kích thước dump trong manifest, số dòng, EC2 instance type và điều kiện mạng để kết quả có ngữ cảnh.

Với dataset nhỏ, đây là số liệu lab, không phải benchmark production. Gọi “thời gian khôi phục trong lab” nếu chưa tính thời gian phát hiện sự cố và chuẩn bị máy mới. Không tuyên bố hệ thống đã phục hồi sau mất toàn bộ EC2 vì các bài này đang dùng DB mới trên cùng máy.

---PAGE---
## 4 Chứng minh chọn được phiên cũ
Thực hiện lúc nhóm tạm ngừng sửa DB/config; tạm dừng cron backup theo hướng dẫn Đức nếu cần tránh các phiên xen giữa. Không xóa dữ liệu gốc.

1. Hoàng chạy backup và ghi RUN_A. Kiểm tra row item_id=1 có quantity=3, config version=1.
2. Thay đổi một dòng mẫu và phiên bản config bằng các lệnh dưới.
3. Chạy backup mới và ghi RUN_B.
4. Restore RUN_A và RUN_B vào hai DB mới. RUN_A phải có giá trị cũ; RUN_B phải có giá trị mới.

```bash
sudo -u postgres psql -X -v ON_ERROR_STOP=1 -d cloud_backup_demo -c 'UPDATE demo_inventory SET quantity=999 WHERE item_id=1;'
sudo sed -i 's/^version=1$/version=2/' /opt/cloudbackup/demo-config/app.conf
sudo /opt/cloudbackup/.venv/bin/python /opt/cloudbackup/src/backup.py
```

```bash
sudo /opt/cloudbackup/.venv/bin/python /opt/cloudbackup/src/restore_test.py --run-id RUN_A_THAT
sudo /opt/cloudbackup/.venv/bin/python /opt/cloudbackup/src/restore_test.py --run-id RUN_B_THAT
```

Với từng RESTORE_DB, truy vấn SELECT * FROM demo_inventory WHERE item_id=1 và đọc app.conf ở RESTORED_CONFIG tương ứng. So sánh với phiên đã chọn, không so phiên A với nguồn hiện tại vốn đã đổi sang B.

Sau test, thống nhất muốn tiếp tục demo với A hay B. Nếu đưa mẫu về giá trị ban đầu, dùng:

```bash
sudo -u postgres psql -X -v ON_ERROR_STOP=1 -d cloud_backup_demo -c 'UPDATE demo_inventory SET quantity=3 WHERE item_id=1;'
sudo sed -i 's/^version=2$/version=1/' /opt/cloudbackup/demo-config/app.conf
sudo /opt/cloudbackup/.venv/bin/python /opt/cloudbackup/src/backup.py
```

Chỉ dùng hai lệnh hoàn tác trên khi dữ liệu ban đầu đúng là quantity=3 và version=1 như bộ seed; nếu nhóm đã có dữ liệu khác, lưu baseline thật trước khi sửa. Bật lại cron đã tạm dừng và ghi RUN_ID phiên mới nhất.

---PAGE---
## 5 Thử phiên thiếu SUCCESS và file hỏng
Bộ mã có tool tạo fixture trong RUN_ID mới trên cùng prefix; nó không sửa phiên nguồn và không cập nhật last_success. Dùng phiên tốt của Hoàng làm nguồn, dữ liệu giả. Fixture sẽ tạo thêm object S3 có phí nhỏ theo sử dụng.

Tạo phiên thiếu SUCCESS:

```bash
sudo /opt/cloudbackup/.venv/bin/python /opt/cloudbackup/tools/make_restore_fixture.py --source-run RUN_TOT_THAT --kind incomplete
```

Ghi FIXTURE_RUN_ID in ra. List phải báo INCOMPLETE. Restore fixture đó phải exit 1, không có DB mới:

```bash
sudo /opt/cloudbackup/.venv/bin/python /opt/cloudbackup/src/list_backups.py
sudo /opt/cloudbackup/.venv/bin/python /opt/cloudbackup/src/restore_test.py --run-id FIXTURE_ID_THAT
echo "EXPECTED_1=$?"
```

Tạo phiên có dump bị đổi một byte nhưng manifest vẫn giữ checksum dump gốc:

```bash
sudo /opt/cloudbackup/.venv/bin/python /opt/cloudbackup/tools/make_restore_fixture.py --source-run RUN_TOT_THAT --kind corrupt
sudo /opt/cloudbackup/.venv/bin/python /opt/cloudbackup/src/restore_test.py --run-id FIXTURE_HONG_THAT
echo "EXPECTED_1=$?"
```

Kỳ vọng báo Checksum or size mismatch trước khi tạo DB. Fixture corrupt có SUCCESS marker giả lập nên list vẫn có thể ghi SUCCESS_MARKER; đây chính là lý do phải kiểm tra hash và restore. Manifest/SUCCESS có test_fixture để phân biệt với phiên dùng nghiệm thu. Không dùng các fixture làm dữ liệu nộp tốt hoặc mốc heartbeat.

Ghi các FIXTURE_RUN_ID vào test report. Không sửa hay xóa bản nguồn để tạo lỗi. Sau khi chấm xong, chủ tài khoản có thể dọn đúng fixture đã ghi; script không được cấp DeleteObject để tự dọn S3.

---PAGE---
## 6 Thử lỗi DB và S3
DB sai dùng tool make_error_config.py theo phần Hoàng. Trước khi test, kiểm tra topic đã có trong config chính, và tạo file lỗi mới nếu file cũ chưa có SNS.

S3 lỗi: cần xác nhận role chỉ được ghi backups/*, không có quyền bucket rộng từ policy khác. Cấu hình thử sẽ ghi vào denied-nhom7-test; nếu quyền đúng, upload phải bị từ chối.

```bash
sudo /opt/cloudbackup/.venv/bin/python /opt/cloudbackup/tools/make_error_config.py --kind s3 --out /etc/cloudbackup-error-s3.json
sudo /opt/cloudbackup/.venv/bin/python /opt/cloudbackup/src/backup.py --config /etc/cloudbackup-error-s3.json
echo "EXPECTED_1=$?"
sudo tail -n 15 /var/backups/cloudbackup/backup.log
```

Kỳ vọng BACKUP_FAILED ở S3_UPLOAD, không SUCCESS và có SNS. Nếu exit 0, ghi test không đạt vì role có quyền rộng hơn giả định; không thêm Deny diện rộng lên role chung để ép lỗi. update_state=false bảo đảm lần thử này không thay mốc heartbeat ngay cả khi upload bất ngờ được phép.

## 7 Kiểm tra khóa trong lúc chạy thật
Terminal A trên EC2 giữ khóa tối đa 30 giây; chỉ thử khi không có backup đang chạy:

```bash
sudo /opt/cloudbackup/.venv/bin/python -c 'import sys,time; sys.path.insert(0,"/opt/cloudbackup/src"); from common import lock; c=lock("/var/lock/cloudbackup.lock"); c.__enter__(); print("LOCK HELD",flush=True); time.sleep(30); c.__exit__(None,None,None)'
```

Trong 30 giây đó, terminal B chạy:

```bash
sudo /opt/cloudbackup/.venv/bin/python /opt/cloudbackup/src/backup.py
echo "EXPECTED_75=$?"
```

Kỳ vọng SKIPPED_LOCK, exit 75 và không upload mới. Sau khi terminal A kết thúc, chạy lại backup phải được. Bài timeout subprocess nằm trong test_real_timeout của suite unittest; không cố làm PostgreSQL thật treo để kiểm tra timeout.

---PAGE---
## 8 Kiểm thử tích hợp và kết luận
Phối hợp với Đức/Hưng kiểm tra hai phiên cron, CloudWatch Logs, tuổi backup tăng khi cron tắt, missing data khi EC2 Stop, cảnh báo nhận thật và hồi phục về OK. Không tự Stop máy khi Hoàng hoặc người khác đang làm.

| Kết quả phải lưu | Nội dung |
| --- | --- |
| Backup tốt | RUN_ID, thời gian UTC, S3 object, log |
| Restore tốt | DB mới, config mới, result.json, truy vấn |
| Restore phiên cũ | Giá trị A/B và RUN_ID tương ứng |
| Lỗi DB/S3 | Mã thoát, bước lỗi, state không đổi, cảnh báo |
| Hỏng/thiếu object | Fixture ID, lý do từ chối, không tạo DB |
| Cron/khóa/timeout | Lịch, hai phiên tự động, exit 75, kết quả unit test |
| Cảnh báo ngoài EC2 | Alarm history, metric, giờ nhận email/SMS |

Điền docs/05_Nghiem_thu.md theo kết quả thực tế. Những bài chưa chạy để CHUA_CHAY; lỗi để FAIL. Ghi thời gian/phạm vi test, không sửa thành PASS chỉ vì tài liệu mô tả kết quả mong đợi.

Để thu dữ liệu dễ đọc: mỗi người lưu ảnh theo mã test; log có run_id khớp ảnh S3; che số điện thoại, email và thông tin không cần thiết. Không đưa PEM hoặc credential vào ZIP nộp. Giữ một video luồng backup–restore và một video/ảnh có timestamp cho cảnh báo quá hạn vì demo trực tiếp không đủ thời gian chờ.

## Bàn giao cuối
Test report, các result.json đã chọn, bảng thời gian restore, lỗi còn lại, video/ảnh và danh sách RUN_ID tốt. Nêu rõ nếu SMS chưa đạt. Mô tả đúng giới hạn: logical backup một DB/config, restore lab, không PITR hay tự khôi phục toàn bộ EC2.

Nguồn: PostgreSQL pg_restore — https://www.postgresql.org/docs/15/app-pgrestore.html
