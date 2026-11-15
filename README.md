# CloudBackup — Nhóm 7



Hệ thống tự động sao lưu và khôi phục cơ sở dữ liệu **PostgreSQL** cùng thư mục tệp cấu hình lên **Amazon S3**, tích hợp giám sát tập trung qua **Amazon CloudWatch** (Logs, Custom Metrics, Alarms) và gửi cảnh báo sự cố qua **Amazon SNS**.



---



## 1. Cấu trúc thư mục dự án



```text

cloudbackup_nhom7/

├── src/                        # Mã nguồn chính (Python 3.9+)

│   ├── backup.py               # Sao lưu PostgreSQL + config, tạo manifest, upload S3 & ghi SUCCESS

│   ├── restore_test.py         # Tải bản sao lưu, kiểm tra SHA-256 và khôi phục vào DB/thư mục thử nghiệm

│   ├── list_backups.py         # Liệt kê lịch sử các phiên sao lưu trên S3 (phân biệt COMPLETE / INCOMPLETE)

│   ├── heartbeat.py            # Tính tuổi bản backup thành công gần nhất và đẩy metric lên CloudWatch

│   └── common.py               # Các hàm dùng chung (lock tiến trình, cấu hình, logging, AWS clients)

├── tests/

│   └── test_lab.py             # Bộ kiểm thử đơn vị (18/18 PASS trên Amazon Linux 2023)

├── tools/                      # Công cụ hỗ trợ tạo template AWS, cấu hình lỗi và fixture kiểm thử

│   ├── make_aws_templates.py

│   ├── make_error_config.py

│   └── make_restore_fixture.py

├── deploy/                     # Cấu hình triển khai cron, logrotate và CloudWatch Agent

│   ├── cloudbackup-backup.cron

│   ├── cloudbackup-heartbeat.cron

│   ├── cloudbackup.logrotate

│   └── cloudwatch-agent.json

├── sql/

│   └── seed.sql                # Script tạo bảng demo_inventory và dữ liệu mẫu

├── demo-config/                # Thư mục cấu hình ứng dụng mẫu phục vụ kiểm thử sao lưu

├── docs/

│   └── 05_Nghiem_thu.md        # Biên bản nghiệm thu và kết quả kiểm thử thực tế (T01–T13)

├── evidence/                   # Minh chứng kiểm thử (result.json và ảnh chụp AWS Console)

├── config.example.json         # Tệp cấu hình mẫu (không chứa thông tin nhạy cảm)

├── requirements.txt            # Khai báo thư viện tối thiểu

├── requirements.lock.txt       # Danh sách phiên bản thư viện thực tế trích xuất từ EC2

└── VALIDATION.md               # Mô tả thiết kế bộ kiểm thử offline

```



---



## 2. Môi trường triển khai & Cài đặt



Hệ thống đã được triển khai và kiểm thử trên **AWS EC2 (`ap-southeast-1`)** với cấu hình:

- **Hệ điều hành:** Amazon Linux 2023 (`t3.micro`)

- **Cơ sở dữ liệu:** PostgreSQL 15.19 (`cloud_backup_demo`)

- **Ngôn ngữ & Thư viện:** Python 3.9.25 (`boto3==1.42.97`, `botocore==1.42.97`)

- **Phân quyền:** Sử dụng **IAM Instance Profile** gắn trực tiếp vào EC2 (không lưu AWS Access Key hay mật khẩu trong mã nguồn).



### Các bước cài đặt từ đầu trên EC2



```bash

# 1. Tạo môi trường ảo Python và cài đặt đúng phiên bản thư viện đã khóa

sudo mkdir -p /opt/cloudbackup

# (Copy mã nguồn vào /opt/cloudbackup)

cd /opt/cloudbackup

sudo python3 -m venv .venv

sudo /opt/cloudbackup/.venv/bin/pip install -r requirements.lock.txt



# 2. Khởi tạo cơ sở dữ liệu mẫu

sudo -u postgres psql -c "CREATE DATABASE cloud_backup_demo;"

sudo -u postgres psql -d cloud_backup_demo -f /opt/cloudbackup/sql/seed.sql



# 3. Tạo tệp cấu hình vận hành từ bản mẫu và điền S3 Bucket / SNS Topic ARN

sudo cp /opt/cloudbackup/config.example.json /etc/cloudbackup.json

sudo chmod 600 /etc/cloudbackup.json

```



---



## 3. Hướng dẫn vận hành (CLI)



Mọi tác vụ sử dụng chung tệp cấu hình `/etc/cloudbackup.json`:



```bash

# Chạy sao lưu thủ công

sudo /opt/cloudbackup/.venv/bin/python /opt/cloudbackup/src/backup.py --config /etc/cloudbackup.json



# Liệt kê danh sách các phiên sao lưu trên S3

sudo /opt/cloudbackup/.venv/bin/python /opt/cloudbackup/src/list_backups.py --config /etc/cloudbackup.json



# Khôi phục kiểm thử một phiên cụ thể (tạo DB mới dạng cloud_restore_<id> và thư mục riêng)

sudo /opt/cloudbackup/.venv/bin/python /opt/cloudbackup/src/restore_test.py --config /etc/cloudbackup.json --run-id <RUN_ID>



# Chạy kiểm tra tuổi bản sao lưu và đẩy metric BackupAgeSeconds lên CloudWatch

sudo /opt/cloudbackup/.venv/bin/python /opt/cloudbackup/src/heartbeat.py --config /etc/cloudbackup.json

```



### Lịch chạy tự động (Cron) & Cảnh báo

- Cấu hình trong `deploy/`:

  - **Backup:** chạy mỗi 5 phút (`*/5 * * * *`) trong giai đoạn demo/kiểm thử.

  - **Heartbeat:** chạy mỗi 1 phút (`* * * * *`) độc lập với tiến trình backup, gửi metric `BackupAgeSeconds` (namespace `CloudBackup/Nhom7`).

  - **CloudWatch Alarm (`cloudbackup-nhom7-age`):** ngưỡng demo `900` giây (`TreatMissingData=breaching`), gửi thông báo tới **SNS Topic** khi quá hạn backup hoặc EC2 ngừng hoạt động.

- *Lưu ý sau demo:* Khi chuyển sang lịch sao lưu hằng ngày (`01:00 GMT+7` / `18:00 UTC`), cần cập nhật đồng bộ ngưỡng alarm lên `93600` giây (26 giờ) để tránh cảnh báo giả.



---



## 4. Quy ước mã thoát (Exit Codes)



| Mã thoát | Ý nghĩa |

| :---: | :--- |

| **`0`** | Thành công: dữ liệu đã tải lên S3, ghi tệp dấu hiệu `SUCCESS.json` và cập nhật `last_success.json`. |

| **`1`** | Lỗi khởi tạo hoặc lỗi trong quá trình sao lưu/khôi phục (không ghi `SUCCESS.json`, kích hoạt cảnh báo SNS). |

| **`2`** | Dữ liệu đã commit lên S3 nhưng cập nhật tệp trạng thái cục bộ thất bại. |

| **`75`** | Bỏ qua lượt chạy (`SKIPPED_LOCK`) do đang có một tiến trình sao lưu khác giữ khóa. |



---



## 5. Kết quả kiểm thử & Nghiệm thu



- **Kiểm thử đơn vị (`tests/test_lab.py`):** Chạy trực tiếp trên EC2 Amazon Linux 2023 đạt **`18/18 PASS`** (bao gồm cả ca kiểm thử giới hạn thời gian `test_real_timeout`).

- **Kiểm thử tích hợp & Nghiệm thu (T01 – T13):** Chi tiết số liệu từng ca kiểm thử, thời gian khôi phục lab (trung bình **0,526 giây** trên 100 bản ghi), độ trễ phát hiện sự cố CloudWatch Alarm và các minh chứng ảnh/JSON được lưu đầy đủ tại:

  - Biên bản nghiệm thu: [`docs/05_Nghiem_thu.md`](docs/05_Nghiem_thu.md)

  - Thư mục minh chứng: [`evidence/`](evidence/)



---



## 6. Giới hạn phạm vi hệ thống



- Hệ thống thực hiện **full logical backup** (`pg_dump -Fc`) cho một cơ sở dữ liệu mẫu (`cloud_backup_demo`) và thư mục cấu hình chỉ định; giới hạn mặc định tối đa `200 MiB/tệp`, timeout lệnh DB `120 giây`.

- Khôi phục kiểm thử được thực hiện vào cơ sở dữ liệu tách biệt trên cùng máy chủ EC2 để xác minh tính toàn vẹn dữ liệu và cấu hình; không phải giải pháp Point-in-Time Recovery (PITR) hay tự động phục hồi toàn bộ hạ tầng EC2.

- **Kênh cảnh báo SMS:** Luồng phát sự kiện tới Amazon SNS hoạt động đúng thiết kế và đã xác minh nhận thông báo thực tế qua kênh **Email**; riêng việc gửi tin nhắn **SMS** tới điện thoại bị chặn ở cấp tài khoản AWS do chưa đăng ký gói dịch vụ *AWS End User Messaging SMS (`PinpointSmsVoiceV2`)* (chi tiết xem tại `docs/05_Nghiem_thu.md` và `evidence/T13b_T13c_sns_sms_blocked.png`).

