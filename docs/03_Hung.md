# Hướng dẫn phần Hưng
IAM CloudWatch SNS và SMS

## 1 Kiểm tra SMS ngay ngày đầu
Bạn có thể bắt đầu trước khi Hoàng viết xong backup. Xác nhận tài khoản sở hữu tài nguyên, Region thực tế và quyền truy cập của mình. Dùng cùng tài khoản/Region với EC2 và bucket để tránh cấu hình chéo không cần thiết.

AWS SNS dùng AWS End User Messaging SMS để chuyển tin nhắn. Với số Việt Nam (+84), tài liệu AWS hiện liệt kê yêu cầu đăng ký sender ID. Vì vậy chỉ xác minh số trong SMS sandbox chưa đủ để bảo đảm gửi được tin. Đừng hứa với nhóm rằng vài bước tạo topic chắc chắn hoàn thành SMS.

Trong AWS Console, mở SNS → Text messaging/SMS và AWS End User Messaging SMS. Kiểm tra sandbox, destination phone numbers, spending limit và origination identities. Với tài khoản sandbox, thêm số điện thoại của thành viên đồng ý nhận tin; dùng E.164: +84 rồi bỏ số 0 đầu, ví dụ 09... thành +849...; xác minh bằng mã OTP thật.

Kiểm tra sender ID/origination identity nào được tài khoản phép dùng cho Việt Nam; nếu cần đăng ký, xem yêu cầu hồ sơ và trạng thái Complete. Hướng dẫn đăng ký có thể yêu cầu tài liệu tổ chức/thương hiệu. Không khai thông tin giả để vượt bước này. Nếu chưa có identity hợp lệ, báo nhóm ngay trong ngày đầu và trao đổi giảng viên/chủ tài khoản về phương án được chấp nhận.

Trong cấu hình SMS của SNS, chọn loại tin Transactional và default sender ID đã được cấp phép nếu áp dụng. Kiểm tra resource policy cho phép SNS dùng origination identity theo tài liệu AWS. Vì Alarm gửi SNS trực tiếp, thiết lập mặc định phải hoạt động cho cả thông báo từ Python lẫn CloudWatch; chỉ gắn thuộc tính SenderID vào một lệnh test sẽ không đủ kiểm chứng đường Alarm.

Kiểm soát số lần gửi thử, phí và delivery status. Email là kênh dự phòng để chẩn đoán; SMS vẫn ghi chưa đạt cho tới khi điện thoại nhận thật từ luồng hệ thống.

Nguồn cần mở đối chiếu trên tài khoản:
[1] https://docs.aws.amazon.com/sns/latest/dg/sns-sms-sandbox.html
[2] https://docs.aws.amazon.com/sms-voice/latest/userguide/phone-numbers-sms-by-country.html
[3] https://docs.aws.amazon.com/sms-voice/latest/userguide/registrations-vietnam.html
[4] https://docs.aws.amazon.com/sms-voice/latest/userguide/registrations.html

---PAGE---
## 2 Tạo topic và kiểm tra email trước
Trong SNS Console đúng Region, tạo Standard topic tên cloudbackup-nhom7-alerts. Tạo subscription Email và mở email xác nhận. Sau khi điều kiện SMS ở bước 1 đã sẵn sàng, thêm subscription SMS tới số đã được phép nhận.

Từ Console của topic, dùng Publish message gửi một tin thử ngắn. Lưu MessageId và giờ nhận. Publish thành công chỉ xác nhận SNS đã nhận yêu cầu; không chứng minh nhà mạng đã chuyển tin.

Trên EC2, mở cấu hình và điền ARN topic thật:

```bash
sudo nano /etc/cloudbackup.json
sudo /opt/cloudbackup/.venv/bin/python -m json.tool /etc/cloudbackup.json
```

Giá trị sns_topic_arn có dạng arn:aws:sns:REGION:ACCOUNT_ID:cloudbackup-nhom7-alerts. Không đổi database hoặc đường dẫn Hoàng đang dùng.

## 3 Sinh policy và alarm đúng tài khoản
Lấy AWS account ID 12 chữ số từ Console hoặc STS. Trên EC2, thay 123456789012 bằng ID thật:

```bash
sudo /opt/cloudbackup/.venv/bin/python /opt/cloudbackup/tools/make_aws_templates.py --account-id 123456789012
sudo cat /opt/cloudbackup/generated/ec2-runtime-policy.json
sudo cat /opt/cloudbackup/generated/topic-alarm-statement.json
sudo cat /opt/cloudbackup/generated/alarm.json
```

Tool chỉ ghi file local, chưa cấp quyền hoặc tạo alarm. Kiểm tra bucket, prefix, Region, account và topic ARN. Trong IAM Console → role đang gắn EC2 → Add permissions → Create inline policy → JSON, thêm nội dung ec2-runtime-policy.json sau khi đọc.

Policy gồm Put/Get object dưới backups/*, ListBucket giới hạn prefix, SNS Publish đúng topic, PutMetricData đúng namespace và quyền ghi log group của nhóm. Không cần cấp AdministratorAccess cho EC2. Policy không có quyền tạo SNS, tạo alarm, tạo log group hay xóa S3; người triển khai dùng quyền quản trị phù hợp để làm các bước đó bằng Console/CloudShell.

Role cũ có thể đã có policy S3 từ tuần 1. Kiểm tra tổng quyền, không tưởng thêm policy hẹp sẽ thu hẹp một policy rộng đang tồn tại. Không xóa role hoặc sửa trust relationship đã chạy đúng chỉ để gắn policy mới.

---PAGE---
## 4 Cho phép Alarm gửi tới SNS
Mở SNS topic → Edit → Access policy. Giữ các statement hiện có; thêm object trong topic-alarm-statement.json vào mảng Statement. Đây chỉ là một statement, không phải toàn bộ policy để thay thế. Lưu lại bản policy cũ trước khi chỉnh.

Statement cho phép service cloudwatch.amazonaws.com thực hiện sns:Publish, giới hạn đúng SourceAccount và SourceArn của alarm cloudbackup-nhom7-age. Nếu đổi tên alarm, phải tạo lại statement phù hợp. Không tạo Deny rộng chặn luôn EC2 hoặc CloudWatch.

Nếu topic sử dụng khóa KMS tùy chỉnh, cần kiểm tra thêm key policy cho bên gửi. Trong lab này chọn topic không bật mã hóa KMS tùy chỉnh để tránh thêm phụ thuộc chưa cần thiết; S3 vẫn giữ mã hóa đang có.

Thử publish từ EC2 bằng đúng role của tiến trình backup. Điền ARN và Region thực tế:

```bash
sudo aws sts get-caller-identity
sudo aws sns publish --region ap-southeast-1 --topic-arn 'ARN_TOPIC_THAT' --message 'Nhom7 test notification from EC2'
```

Kỳ vọng MessageId và email/SMS thật. Nếu aws không nằm trong sudo PATH thì dùng đường dẫn từ command -v aws. Nếu thiếu quyền, sửa đúng role/policy; không chạy aws configure với access key cá nhân trên EC2.

## 5 Tạo CloudWatch log group
Trong CloudWatch Console đúng Region → Logs → Log groups → Create log group: /cloudbackup/nhom7. Đặt retention 14 days hoặc giá trị nhóm thống nhất. Role EC2 chỉ cần ghi stream vào group đã tạo; không tự tạo group trong mã.

Trên Amazon Linux 2023, cài Agent:

```bash
sudo dnf install -y amazon-cloudwatch-agent
sudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl -a fetch-config -m ec2 -c file:/opt/cloudbackup/deploy/cloudwatch-agent.json -s
sudo systemctl enable amazon-cloudwatch-agent
sudo systemctl status amazon-cloudwatch-agent --no-pager
```

Nếu kho không có package, tải gói chính thức đúng OS/CPU theo [5]; kiểm tra uname -m để chọn amd64 hay arm64. Không lấy URL amd64 cho máy aarch64. Trên Ubuntu dùng gói Ubuntu .deb theo cùng nguồn, không dùng dnf.

---PAGE---
## 6 Kiểm tra log và metric thật
Nhờ Hoàng chạy một backup hoặc một cấu hình lỗi riêng. Trong CloudWatch → /cloudbackup/nhom7 → stream INSTANCE_ID/backup, tìm BACKUP_SUCCESS hoặc BACKUP_FAILED và run_id tương ứng.

Nếu không thấy log, kiểm tra:

```bash
sudo tail -n 10 /var/backups/cloudbackup/backup.log
sudo tail -n 60 /opt/aws/amazon-cloudwatch-agent/logs/amazon-cloudwatch-agent.log
sudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl -m ec2 -a status
```

Agent chạy root để đọc log trong thư mục quyền 700. Không sửa log thành world-readable để giải quyết AccessDenied từ API. Kiểm tra Region, log group đã có và policy đúng ARN.

Đức chạy heartbeat; bạn mở CloudWatch → Metrics → All metrics → CloudBackup/Nhom7. Chọn đúng Project=Nhom7, Environment=demo, metric BackupAgeSeconds. Sau backup mới, giá trị gần 0 rồi tăng theo thời gian; mỗi backup tốt làm tuổi giảm.

```bash
sudo /opt/cloudbackup/.venv/bin/python /opt/cloudbackup/src/heartbeat.py
```

Nếu lần đầu metric chưa xuất hiện ngay, chờ việc ingest/display rồi kiểm tra lại; đừng tạo nhiều metric có tên khác để thử. Không dùng run_id làm dimension.

## 7 Tạo alarm bằng Console
Chọn metric trên → Create alarm. Statistic Maximum; Period 1 minute; Static threshold Greater than 900; Datapoints to alarm 2 out of 2; Missing data treatment: Treat missing data as bad/breaching. Alarm name cloudbackup-nhom7-age. Action In alarm và OK đều gửi đến cloudbackup-nhom7-alerts. Không chọn Stop/Terminate instance action.

Các giá trị này phải khớp generated/alarm.json. Nếu Console thay đổi vị trí mục, đối chiếu tên thông số và tài liệu [6]. Khởi đầu phải có backup thành công và metric hợp lệ để alarm ổn định ở OK; nếu tạo khi chưa có metric, ALARM là kết quả phù hợp với cấu hình missing-data.

---PAGE---
## 8 Cách tạo alarm bằng CloudShell nếu muốn
Đây là cách thay thế Console, không cần thực hiện cả hai. Mở CloudShell bằng người dùng có quyền cloudwatch:PutMetricAlarm trong đúng Region. Upload file alarm.json đã sinh hoặc tạo file từ nội dung JSON đã kiểm tra.

Trên CloudShell, lệnh một dòng:

```bash
aws cloudwatch put-metric-alarm --region ap-southeast-1 --cli-input-json file://alarm.json
aws cloudwatch describe-alarms --region ap-southeast-1 --alarm-names cloudbackup-nhom7-age
```

Đổi Region theo thực tế. Không cấp PutMetricAlarm cho EC2 chỉ để chạy hai lệnh này; role runtime chỉ cần PutMetricData. Trong Console, kiểm tra action đã Enabled, topic ARN đúng và state reason.

## 9 Kiểm thử hai đường cảnh báo
Đường thứ nhất: Hoàng chạy backup với config DB sai. Cần log BACKUP_FAILED → NOTIFICATION_PUBLISHED → email/SMS thật. Nếu config lỗi được tạo trước khi có topic, tạo config lỗi mới để nhận sns_topic_arn hiện tại.

Đường thứ hai: Đức tắt riêng cron backup nhưng giữ heartbeat. Sau tuổi backup vượt 900 giây và đánh giá đủ điều kiện, CloudWatch chuyển ALARM → SNS → email/SMS. Sau đó thử Stop EC2 trong khung giờ thống nhất để kiểm tra thiếu metric. Hai bài này phải được khôi phục về OK trước khi kết thúc.

CloudWatch Alarm gửi SNS khi chuyển trạng thái; không mặc định gửi một SMS lặp lại mỗi phút khi vẫn ALARM. Mỗi job lỗi gửi SNS trực tiếp có thể tạo tin lặp nếu cron tiếp tục lỗi, nên sửa lỗi hoặc tạm dừng đúng lịch sau bài test.

| Có gì rồi | Kết luận đúng |
| --- | --- |
| Publish có MessageId | SNS nhận yêu cầu; chưa kết luận SMS đến |
| Email đến, SMS chưa đến | Đường topic có hoạt động; tiếp tục chẩn đoán SMS |
| Alarm ở ALARM nhưng không có tin | Xem action, topic policy, KMS nếu có, trạng thái subscription |
| SMS đến điện thoại | Lưu giờ nhận, đối chiếu loại lỗi/run_id hoặc alarm; che số khi nộp |

---PAGE---
## 10 Bàn giao và xử lý vướng mắc SMS
Ghi trạng thái riêng cho email, SMS từ backup và SMS từ Alarm. Lưu ARN topic, tên alarm, cấu hình metric, policy đã áp dụng, log Agent và ảnh điện thoại. Không gửi cả credentials hoặc ảnh số điện thoại chưa che vào báo cáo công khai.

Nếu SMS chưa hoạt động, tổng hợp: Region, sandbox status, số nhận đã verified hay chưa, loại origination identity, trạng thái registration, MessageId, delivery failure reason và thời điểm thử. Không gửi đi gửi lại hàng chục lần để đoán lỗi. Xem delivery-status logging trong SNS nếu tài khoản cho phép và ghi nhận phí phát sinh.

Đối với sender ID yêu cầu đăng ký ở Việt Nam, thời gian xét duyệt có thể nằm ngoài khả năng kiểm soát của nhóm. Nếu không đủ điều kiện tài khoản/hồ sơ, cần quyết định sớm với giảng viên về tài nguyên được phép hoặc điều chỉnh yêu cầu. Không tự gắn email là “SMS đã hoàn thành”.

Khi Đức chuyển backup sang hằng ngày, đổi threshold từ 900 sang 93600 giây trong alarm và overdue_seconds trong JSON. Nếu dùng tool sinh JSON, chạy lại make_aws_templates.py sau khi sửa config rồi áp dụng alarm.json. Sinh file mới không tự cập nhật AWS.

Theo dõi chi phí CloudWatch custom metric/alarm/Logs và SMS. Dùng namespace/dimensions cố định. Budget cảnh báo không mặc định là trần chặn chi tiêu. Không xóa log group hay bucket minh chứng trước khi nhóm được chấm xong.

## Kiểm tra cuối phần Hưng
Policy EC2 đúng role; SNS email xác nhận; số SMS và origination identity hợp lệ; log thật xuất hiện trong CloudWatch; metric đúng dimensions; alarm OK trước test; có ALARM từ quá hạn và thiếu metric; có hồi phục OK; đủ bằng chứng nhận tin.

## Nguồn kỹ thuật bổ sung
[5] CloudWatch Agent download: https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/download-CloudWatch-Agent-on-EC2-Instance-commandline-first.html
[6] Missing data: https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/alarms-and-missing-data.html
[7] Agent prerequisites: https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/prerequisites.html
[8] SNS originating identities: https://docs.aws.amazon.com/sns/latest/dg/channels-sms-originating-identities.html
