# Hướng dẫn phần Đức
Tích hợp lịch chạy lịch sử và tín hiệu giám sát

## 1 Đầu vào và trách nhiệm
Hoàng đã cài mã ở /opt/cloudbackup, có /etc/cloudbackup.json và ít nhất một phiên backup thành công. Dùng cùng EC2 và cấu hình; không tạo một bộ cron khác trên máy của Đức. Bạn chịu trách nhiệm xem lịch sử, cron, heartbeat, đồng bộ với Hưng và bộ hướng dẫn chạy lại.

Trong terminal EC2:

```bash
sudo /opt/cloudbackup/.venv/bin/python /opt/cloudbackup/src/list_backups.py
sudo cat /var/backups/cloudbackup/last_success.json
timedatectl
date
date -u
```

Lịch sử bỏ qua test-backup.txt tuần 1. SUCCESS_MARKER chỉ là đủ tên object, chưa có nghĩa đã restore đạt. Dương ghi kết quả restore riêng trong result.json và bảng nghiệm thu.

## 2 Cài cron backup
Kiểm tra tất cả lịch hiện có trước khi thêm. Nếu trước đây đã làm theo tài liệu cũ, có thể còn file /etc/cron.d/cloudbackup hoặc root crontab; phải thống nhất chỉ có một lịch backup hoạt động.

```bash
sudo ls -l /etc/cron.d
sudo crontab -l
sudo grep -R 'backup.py' /etc/cron.d /etc/crontab
```

Nếu có lịch cũ của chính dự án, lưu nội dung rồi vô hiệu hóa đúng lịch đó trước khi cài lịch mới; không xóa cron của dịch vụ khác. Sau đó:

```bash
sudo install -m 644 /opt/cloudbackup/deploy/cloudbackup-backup.cron /etc/cron.d/cloudbackup-backup
sudo systemctl enable --now crond
sudo cat /etc/cron.d/cloudbackup-backup
sudo systemctl is-active crond
```

Amazon Linux dùng crond; Ubuntu dùng cron. File mẫu đã có newline cuối, PATH và user root. Không chạy crontab /etc/cron.d/... vì định dạng cron.d có cột user riêng.

Chờ qua hai mốc phút chia hết cho 5. Ví dụ cài lúc 14:02, quan sát khoảng sau 14:05 và 14:10. Lệnh tail báo chưa có file trước lần đầu là bình thường.

```bash
sudo tail -n 30 /var/log/cloudbackup-cron.log
sudo /opt/cloudbackup/.venv/bin/python /opt/cloudbackup/src/list_backups.py
```

Pass khi có hai RUN_ID khác nhau do cron tạo, log đúng thời gian và đủ object trên S3. Không dùng hai lần chạy tay làm bằng chứng cron.

---PAGE---
## 3 Cài heartbeat sau khi Hưng cấp quyền metric
Heartbeat đọc last_success.json của Hoàng, tính số giây kể từ backup thành công rồi gửi custom metric. Nó chạy độc lập với job backup; khi backup cron bị tắt, heartbeat vẫn báo tuổi backup tăng.

Trước khi cài lịch, nhờ Hưng xác nhận role có cloudwatch:PutMetricData cho namespace CloudBackup/Nhom7.

```bash
sudo /opt/cloudbackup/.venv/bin/python /opt/cloudbackup/src/heartbeat.py
echo "HEARTBEAT_EXIT=$?"
sudo install -m 644 /opt/cloudbackup/deploy/cloudbackup-heartbeat.cron /etc/cron.d/cloudbackup-heartbeat
sudo tail -n 10 /var/log/cloudbackup-heartbeat.log
```

Kỳ vọng HEARTBEAT_OK, age_seconds hợp lý và exit 0. Mỗi phút sẽ có thêm một dòng. Nếu state thiếu/hỏng, giá trị vượt overdue_seconds và state=INVALID_OR_MISSING_STATE; đây là trạng thái cần điều tra, không phải tín hiệu khỏe.

Đối chiếu với Hưng chính xác 4 trường: namespace CloudBackup/Nhom7, metric BackupAgeSeconds, Project=Nhom7, Environment=demo. Nếu alarm theo nhầm dimensions, nó sẽ tưởng dữ liệu mất dù một metric khác vẫn được gửi.

## 4 Xoay vòng log
Chỉ cài mẫu khi log path vẫn đúng mặc định. File này không xóa bản backup hay DB restore.

```bash
sudo install -m 644 /opt/cloudbackup/deploy/cloudbackup.logrotate /etc/logrotate.d/cloudbackup
sudo logrotate -d /etc/logrotate.d/cloudbackup
```

-d chỉ kiểm tra cấu hình. Mẫu giữ 7 bản log xoay vòng, nén bản cũ. Kiểm tra lịch logrotate của OS để biết nó thực sự được gọi tự động. Không bật thêm một cron logrotate trùng với timer có sẵn.

## 5 Kiểm tra khóa và giới hạn chạy
Mã lấy flock ngay bên trong backup.py nên cả cron và lệnh tay dùng chung /var/lock/cloudbackup.lock. Các cấu hình thử lỗi cũng giữ nguyên lock_file. Exit 75 là SKIPPED_LOCK, không tạo một phiên backup tốt mới.

Chạy test Linux từ bộ mã để kiểm tra tranh chấp khóa và timeout subprocess:

```bash
cd /opt/cloudbackup
sudo /opt/cloudbackup/.venv/bin/python -m unittest discover -s tests -v
```

Đừng chỉ gọi hai backup tuần tự rồi kết luận đã chống chạy chồng. Dương có bước giữ khóa có kiểm soát trong hướng dẫn kiểm thử. Giới hạn DB command là 120 giây, API có timeout/retry hữu hạn; chưa phải SLA thời gian tổng của một job lớn.

---PAGE---
## 6 Thử bỏ lỡ lịch backup
Chỉ làm sau khi Hưng tạo alarm và đã xác nhận OK. Ghi giờ bắt đầu. Tạm đưa đúng file lịch backup ra khỏi /etc/cron.d; giữ lịch heartbeat hoạt động.

```bash
sudo mv /etc/cron.d/cloudbackup-backup /var/backups/cloudbackup/backup-cron.paused
sudo tail -n 5 /var/log/cloudbackup-heartbeat.log
```

Chỉ chạy mv nếu backup-cron.paused chưa có; nếu đã có thì kiểm tra trạng thái lần thử trước, không ghi đè. Trong khi test, không chạy backup tay vì nó sẽ làm mới state. Sau hơn 15 phút kể từ lần backup tốt cuối, metric vượt 900 giây; Hưng theo dõi Alarm và SNS. Thời gian Alarm thực tế có độ trễ đánh giá, không hứa chính xác từng phút.

Khôi phục lịch sau khi thu minh chứng:

```bash
sudo mv /var/backups/cloudbackup/backup-cron.paused /etc/cron.d/cloudbackup-backup
sudo chmod 644 /etc/cron.d/cloudbackup-backup
sudo /opt/cloudbackup/.venv/bin/python /opt/cloudbackup/src/backup.py
sudo /opt/cloudbackup/.venv/bin/python /opt/cloudbackup/src/heartbeat.py
```

Kỳ vọng sau chu kỳ đánh giá, alarm về OK. Hưng lưu ảnh Alarm history cùng timestamp của log/điện thoại. Việc cưỡng bức alarm bằng set-alarm-state không được tính là phát hiện quá hạn thật.

## 7 Thử khi EC2 dừng
Chọn khung giờ cả nhóm thống nhất, không có backup/restore đang chạy. Hưng hoặc chủ tài khoản Stop instance từ EC2 Console. CloudWatch ở bên ngoài EC2 tiếp tục đánh giá; thiếu metric phải dẫn tới alarm theo TreatMissingData=breaching.

Không trông chờ script trên EC2 tự gửi tin sau khi máy đã Stop. Ghi lần metric cuối, thời gian ALARM và thời gian SMS/email. Khi Start lại, kiểm tra public IP mới, SSH, PostgreSQL, crond, CloudWatch Agent và heartbeat; chạy backup tốt để xác nhận hồi phục.

Alarm chỉ nói quá hạn hoặc mất tín hiệu giám sát; nguyên nhân có thể là EC2, mạng, IAM hoặc heartbeat. Đừng gắn nhãn chắc chắn “EC2 chết” chỉ dựa trên alarm này.

---PAGE---
## 8 Chuyển lịch sau demo
Để tránh tạo quá nhiều bản sao, chuyển sang một lần/ngày. Chỉ dùng lịch dưới nếu timedatectl xác nhận cron đang dùng UTC:

```bash
sudo nano /etc/cron.d/cloudbackup-backup
```

Giữ SHELL/PATH và thay dòng tác vụ bằng một dòng:

```text
0 18 * * * root /opt/cloudbackup/.venv/bin/python /opt/cloudbackup/src/backup.py --config /etc/cloudbackup.json >> /var/log/cloudbackup-cron.log 2>&1
```

18:00 UTC tương ứng 01:00 Việt Nam ngày kế tiếp. Nếu server dùng Asia/Ho_Chi_Minh, dùng 0 1. Không vừa chuyển timezone vừa giữ lịch cũ mà không kiểm tra lại.

Sửa overdue_seconds trong /etc/cloudbackup.json từ 900 thành 93600 (26 giờ), báo Hưng cập nhật threshold alarm cùng giá trị. Heartbeat vẫn mỗi phút. Nếu chỉ sửa JSON, alarm trên AWS không tự đổi; Hưng phải áp dụng lại alarm.json hoặc chỉnh Console.

## 9 Bàn giao và chuẩn bị demo
Giữ README khớp lệnh thật, ghi OS, phiên bản, Region, đường dẫn, lịch và ngưỡng cuối cùng. Thống nhất một commit/tag để cả nhóm sử dụng; không sửa trực tiếp khác nhau trên EC2 trước giờ demo.

Bạn phải trình bày được: cron kích hoạt gì; vì sao có khóa; lịch sử chọn phiên thế nào; heartbeat đo tuổi bản tốt thay vì chỉ đo tiến trình còn sống; tại sao Alarm vẫn hoạt động khi EC2 dừng.

| Minh chứng | Tiêu chí |
| --- | --- |
| Hai phiên tự động | Khác run_id, đúng lịch, log và S3 khớp |
| Heartbeat | Metric đúng namespace/dimensions, không chứa run_id trong dimension |
| Tắt cron | Tuổi backup tăng, alarm và thông báo thật |
| Stop EC2 | Mất metric được phát hiện ngoài EC2 |
| Hồi phục | Backup mới tốt, alarm về OK |

Chỉ dọn local backups/restore DB sau khi nhóm đã chọn và lưu phiên minh chứng. Bộ mã không tự xóa để tránh mất bản cần nộp; theo dõi df -h và du -sh /var/backups/cloudbackup trong sprint.

Nguồn: CloudWatch missing data — https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/alarms-and-missing-data.html
