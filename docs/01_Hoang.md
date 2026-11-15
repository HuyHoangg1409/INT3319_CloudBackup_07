# Hướng dẫn phần Hoàng
PostgreSQL và configuration rồi backup lên S3

## Đọc trước khi bắt đầu
Mục tiêu: tạo dữ liệu mẫu trên EC2, sao lưu database và file cấu hình, đưa bản sao lên S3, rồi kiểm tra có thể khôi phục. Bạn làm từng khối lệnh nhỏ; đọc kết quả và tiêu chí đạt trước khi sang khối tiếp theo. Không dán cả tài liệu một lượt.

Chỉ phần 2A chạy trong PowerShell của Windows. Tất cả khối bash còn lại chạy trong terminal EC2 mở từ Connect. Không copy dòng bắt đầu bằng ``` hoặc dấu nhắc PS ...>, $, # của terminal. Các dấu > và < nằm bên trong lệnh backup/restore lại là một phần của lệnh, cần giữ nguyên.

Nếu gặp ERROR, FAILED, AccessDenied, Permission denied hoặc Traceback ngoài bài thử lỗi có chủ đích: dừng khối đó, chụp cả lệnh và kết quả. Lệnh trước lỗi mà vẫn chạy tiếp có thể khiến lỗi sau khó hiểu hơn.

| Ký hiệu / công cụ | Hiểu nhanh |
| --- | --- |
| sudo | Chạy lệnh với quyền quản trị Linux; không phải cấp quyền IAM AWS |
| sudo -u postgres | Chạy dưới tài khoản Linux postgres để thao tác DB nội bộ |
| $HOME | Thư mục của người dùng đang đăng nhập; ec2-user thường là /home/ec2-user |
| /opt/cloudbackup | Thư mục chứa chương trình Python và dữ liệu mẫu |
| /etc/cloudbackup.json | Cấu hình vận hành: DB nào, bucket nào, Region nào |
| /var/backups/cloudbackup | Bản sao local, log và thời điểm backup tốt gần nhất |
| echo "...=$?" | Đọc mã thoát của lệnh ngay trước đó trên Bash; 0 thường là thành công |

Lệnh echo kiểm tra mã thoát phải chạy ngay sau lệnh được kiểm tra. Nếu chen ls hoặc lệnh khác vào giữa, $? sẽ là kết quả của lệnh khác đó. Một số lệnh thành công không in gì; dùng bước kiểm tra đi kèm để xác nhận.

---PAGE---

## 1 Đầu ra và cách dùng bộ tài liệu
Bạn làm phần này trước. Kết thúc phải có DB mẫu 100 dòng, hai file config, một phiên S3 gồm database.dump, configuration.tar.gz, manifest.json, SUCCESS.json và RUN_ID để Dương khôi phục. Đức và Hưng dùng chung cấu hình, không tự đổi tên bucket hoặc Region.

Hướng dẫn giả định EC2 tuần 1 chạy Amazon Linux 2023 và dùng ec2-user. Các bước dưới dành cho dữ liệu lab mới. Nếu kết quả hệ điều hành khác, dùng nhánh Ubuntu ở cuối tài liệu; không trộn lệnh dnf với apt. Không tạo lại EC2/IAM/S3 đã làm được ở tuần 1.

Mã đã được kiểm thử logic offline, chưa được chạy trên EC2 của nhóm. Kết quả mong đợi bên dưới là tiêu chí để bạn kiểm tra, không phải kết quả đã có sẵn.

## 2 Chuyển ZIP từ Windows, rồi làm trên terminal EC2 web
Thư mục trên máy Hoàng: D:\Downloads\Kì 1 năm 3\Điện toán đám mây. Trong đó đã có cloud-backup-key.pem và Bo_thuc_hanh_CloudBackup_Nhom7.zip. Dấu > cuối dòng PowerShell là dấu nhắc, không thuộc đường dẫn.

Bước 2A - Chạy trên PowerShell của máy Windows, chưa SSH vào EC2. Dùng dấu nháy để giữ nguyên đường dẫn có khoảng trắng và tiếng Việt:

```powershell
Set-Location -LiteralPath 'D:\Downloads\Kì 1 năm 3\Điện toán đám mây'
Get-ChildItem -Name *.pem, *.zip
```

Giải thích: Set-Location chuyển PowerShell đến đúng thư mục, không chuyển file đi đâu cả. Get-ChildItem liệt kê tên file PEM và ZIP để kiểm tra bạn đang đứng đúng chỗ. Cần nhìn thấy cloud-backup-key.pem và Bo_thuc_hanh_CloudBackup_Nhom7.zip trước khi chạy SCP.

Trong AWS, chọn Region ap-southeast-1, mở EC2 > Instances > i-09e3d76a3f2db386b. Sao chép Public IPv4 address hiện tại, thay PUBLIC_IP bên dưới rồi chạy cả hai dòng trong PowerShell. Không dùng Private IPv4 hoặc dán nguyên URL console.

```powershell
$ec2Address = 'PUBLIC_IP'
scp -i '.\cloud-backup-key.pem' '.\Bo_thuc_hanh_CloudBackup_Nhom7.zip' "ec2-user@${ec2Address}:/home/ec2-user/"
```

Giải thích: $ec2Address lưu địa chỉ máy chủ; -i chọn khóa đăng nhập; file ZIP là nguồn trên Windows; phần sau dấu hai chấm là thư mục đích trên EC2. SCP chỉ sao chép file, không giải nén và không cài chương trình. Nếu lần đầu hiện câu hỏi xác nhận host key, kiểm tra đúng máy chủ và fingerprint trước khi chấp nhận; không bỏ qua cảnh báo host key đã thay đổi.

Kỳ vọng: tiến trình chuyển ZIP đạt 100% và không báo lỗi. Key phải là key của instance; SSH cần đường mạng tới cổng 22 và Security Group cho phép IP hiện tại của máy bạn. Kết nối web thành công chưa đảm bảo SCP từ máy cá nhân cũng hoạt động. Nếu timeout hoặc Permission denied (publickey), dừng và gửi đúng thông báo lỗi để kiểm tra. Không tải file PEM lên EC2.

---PAGE---
## 2 (tiếp) Mở terminal EC2 trên web
Bước 2B - Chọn đúng instance ở trên > Connect, dùng cách kết nối web đã hoạt động ở tuần 1. Từ terminal này, lệnh chạy trên máy EC2. Không chạy lại Set-Location, scp hoặc lệnh ssh của Windows ở đây; EC2 không nhìn thấy ổ D: trên máy bạn.

Hướng dẫn tiếp tục giả định bạn kết nối bằng ec2-user trên Amazon Linux 2023. Kiểm tra tên người dùng và hệ điều hành trước. Nếu hiện ssm-user hoặc ubuntu, dừng để điều chỉnh đường dẫn và lệnh; ZIP ở bước 2A được gửi đến /home/ec2-user, còn $HOME phụ thuộc người dùng đăng nhập.

Từ đây đến hết phần thực hành, tất cả khối bash chạy trong terminal EC2 trên web. Không cần mở thêm phiên SSH từ PowerShell.

```bash
whoami
cat /etc/os-release
ls -lh /home/ec2-user/Bo_thuc_hanh_CloudBackup_Nhom7.zip
aws --version
aws sts get-caller-identity
sudo aws sts get-caller-identity
```

Kỳ vọng: ec2-user; hệ điều hành Amazon Linux 2023; lệnh ls thấy ZIP đã chuyển (nếu báo No such file or directory, quay lại bước 2A); cả hai lệnh STS dùng assumed-role của EC2. Nếu sudo không thấy aws, kiểm tra command -v aws và dùng đường dẫn tuyệt đối. Nếu ARN là IAM User, kiểm tra credential cũ, không tiếp tục mặc định rằng đang dùng role.

Mục đích từng lệnh kiểm tra: whoami xác định người dùng Linux; os-release xác định hệ điều hành để chọn cách cài gói; ls -lh kiểm tra file ZIP và dung lượng; aws --version xác nhận có AWS CLI. Hai lệnh STS cho biết danh tính AWS khi chạy bình thường và khi chạy sudo, vì chương trình backup sẽ chạy bằng sudo.

Account trong kết quả STS phải là 897258608585. ARN mong đợi chứa :assumed-role/ và tên role gắn cho EC2. STS thành công chỉ chứng minh lấy được danh tính AWS, chưa chứng minh có quyền ghi S3. Quyền S3 được kiểm tra bằng bài backup thật ở phần 6.

---PAGE---
## 3 Cài môi trường và đặt mã vào thư mục cố định
Trên Amazon Linux 2023:

```bash
sudo dnf install -y postgresql15 postgresql15-server python3-pip cronie logrotate
python3 --version
pg_dump --version
pg_restore --version
```

Kỳ vọng PostgreSQL client 15.x; Python 3.9 trở lên. Nếu dnf không tìm thấy gói, kiểm tra /etc/os-release và dnf list available 'postgresql*'; lưu lỗi để xử lý kho gói đúng OS, không nâng cấp toàn hệ điều hành tùy tiện.

Mục đích: postgresql15 là bộ lệnh client (psql, pg_dump, pg_restore); postgresql15-server chạy DB; python3-pip hỗ trợ cài thư viện; cronie dành cho lịch backup của Đức; logrotate dành cho quản lý log. -y tự đồng ý cài các gói. Chờ lệnh cài đặt kết thúc rồi mới chạy ba lệnh xem phiên bản.

Điểm kiểm tra: cả pg_dump và pg_restore phải chạy được và cùng major version phù hợp server. Nếu command not found, chưa được đi tiếp. Việc cài gói thành công chưa có nghĩa DB đã khởi tạo hoặc đang chạy.

Giải nén vào thư mục người dùng, sau đó cài mã. Lần đầu phải chưa có /opt/cloudbackup. Nếu đã có từ lần làm trước, kiểm tra nội dung và sao lưu phiên cũ trước khi cập nhật; không ghi đè cấu hình chạy thật.

```bash
mkdir -p "$HOME/cloudbackup-unpack"
python3 -m zipfile -e "$HOME/Bo_thuc_hanh_CloudBackup_Nhom7.zip" "$HOME/cloudbackup-unpack"
ls "$HOME/cloudbackup-unpack/cloudbackup_nhom7"
sudo test ! -e /opt/cloudbackup && sudo install -d -m 755 /opt/cloudbackup
```

Giải thích: mkdir -p tạo chỗ giải nén; python3 -m zipfile -e giải nén ZIP; ls phải thấy src, sql, tools, tests và config.example.json. Lệnh test ! -e kiểm tra thư mục /opt/cloudbackup chưa tồn tại; && chỉ tạo thư mục khi điều kiện đúng. Chạy ngay sau lệnh đó:

```bash
echo "NEW_INSTALL_DIR_EXIT=$?"
```

Kỳ vọng 0 cho lần cài mới. Nếu khác 0, có thể thư mục đã tồn tại hoặc tạo thất bại: dừng để xem bản đang có, không coi việc terminal im lặng là thành công.

Chỉ chạy đoạn tiếp theo nếu thư mục đích mới được tạo hoặc bạn đã kiểm tra rõ bản hiện có.

```bash
sudo cp -a "$HOME/cloudbackup-unpack/cloudbackup_nhom7/." /opt/cloudbackup/
sudo chown -R root:root /opt/cloudbackup
sudo chmod -R go-w /opt/cloudbackup
sudo python3 -m venv /opt/cloudbackup/.venv
sudo /opt/cloudbackup/.venv/bin/python -m pip install -r /opt/cloudbackup/requirements.txt
sudo /opt/cloudbackup/.venv/bin/python -c 'import boto3; print(boto3.__version__)'
sudo install -d -m 700 /var/backups/cloudbackup
sudo /opt/cloudbackup/.venv/bin/python -m pip freeze | sudo tee /opt/cloudbackup/requirements.lock.txt
```

Giải thích: cp -a chép toàn bộ mã vào nơi cố định; chown đặt chủ sở hữu root; chmod go-w bỏ quyền sửa của nhóm/người khác. venv tạo môi trường Python riêng tên .venv. pip install cài các thư viện từ requirements.txt vào đúng môi trường đó. Lệnh import boto3 phải in phiên bản, không có traceback. install -d -m 700 tạo thư mục backup chỉ root truy cập; tee ghi danh sách phiên bản thư viện vào file.

---PAGE---
## 3 (tiếp) Kiểm tra mã đã cài đúng
Chạy trên EC2 sau khi cài xong:

```bash
sudo ls -l /opt/cloudbackup/src/backup.py /opt/cloudbackup/sql/seed.sql
sudo /opt/cloudbackup/.venv/bin/python --version
sudo /opt/cloudbackup/.venv/bin/python -m pip check
sudo ls -ld /var/backups/cloudbackup
```

Đạt khi: hai file tồn tại; Python chạy được; pip check báo No broken requirements found; thư mục backup thuộc root với quyền drwx------. Nếu ec2-user không ls được bên trong thư mục backup khi thiếu sudo thì phù hợp quyền 700, không cần chmod 777.

requirements.lock.txt ghi đúng phiên bản thư viện đã cài ở EC2 để nộp cùng code. Không dùng pip install boto3 dưới ec2-user rồi gọi Python hệ thống bằng sudo; dễ gặp lỗi thiếu thư viện.

Toàn bộ lệnh chạy chương trình sau này sử dụng /opt/cloudbackup/.venv/bin/python. Không cần activate venv. Mã và config do root sở hữu để cron chạy root không thực thi file mà người khác có thể sửa tùy ý.

---PAGE---
## 4 Khởi tạo PostgreSQL và dữ liệu mẫu
Kiểm tra xem đã có cluster trước khi initdb:

```bash
sudo test -f /var/lib/pgsql/data/PG_VERSION && sudo cat /var/lib/pgsql/data/PG_VERSION
sudo systemctl status postgresql --no-pager
```

Mục đích: PG_VERSION đánh dấu thư mục dữ liệu PostgreSQL đã được khởi tạo; systemctl status xem dịch vụ chạy hay chưa. Nếu có PG_VERSION, không chạy initdb lần nữa. Ở máy mới, status có thể báo inactive hoặc failed do chưa init; đây là trạng thái cần xử lý, không phải bằng chứng dữ liệu đã hỏng.

Nếu chưa có PG_VERSION và chưa có cluster cần giữ, chạy:

```bash
sudo postgresql-setup --initdb
sudo systemctl enable --now postgresql
sudo -u postgres psql -X -d postgres -c 'SELECT version();'
```

Nếu PG_VERSION đã tồn tại, bỏ qua initdb, chỉ start service và kiểm tra. Không xóa thư mục data để chữa lỗi. Nếu công cụ setup không có, chạy rpm -ql postgresql15-server để xác định gói/công cụ; dừng ở bước này nếu môi trường không đúng giả định.

Giải thích: initdb tạo cấu trúc lưu trữ DB lần đầu; enable --now vừa cho phép tự chạy khi EC2 khởi động vừa khởi chạy ngay. SELECT version() kiểm tra server nhận được truy vấn. Nếu thấy phiên bản PostgreSQL và không có lỗi kết nối thì mới tạo DB.

Nếu phần status hiện active (running), server đang chạy. Có thể kiểm tra gọn bằng sudo systemctl is-active postgresql; kết quả mong đợi là active.

Tạo DB mới. Lệnh createdb sẽ báo lỗi nếu tên đã tồn tại; khi đó kiểm tra DB, không drop để chạy lại.

```bash
sudo -u postgres createdb cloud_backup_demo
sudo -u postgres psql -X -v ON_ERROR_STOP=1 -d cloud_backup_demo -f /opt/cloudbackup/sql/seed.sql
sudo -u postgres psql -X -d cloud_backup_demo -c 'SELECT COUNT(*) FROM demo_inventory;'
sudo -u postgres psql -X -d cloud_backup_demo -c 'SELECT * FROM demo_inventory ORDER BY item_id LIMIT 5;'
```

Giải thích: createdb tạo database rỗng tên cloud_backup_demo. psql -f chạy file SQL tạo bảng và thêm 100 sản phẩm; -X bỏ cấu hình psql cá nhân; ON_ERROR_STOP=1 yêu cầu dừng khi SQL lỗi. SELECT COUNT(*) đếm số dòng; SELECT ... LIMIT 5 xem nội dung mẫu, để tránh chỉ đếm mà không biết dữ liệu gì.

Năm dòng đầu phải có item_id từ 1 đến 5, item_name tương ứng San pham 1 đến San pham 5 và quantity lần lượt 3, 6, 9, 12, 15. Đây là kết quả mong đợi từ seed.sql, không phải ảnh kết quả đã chạy trên EC2 của bạn.

Kỳ vọng COUNT = 100, có item_id, item_name, quantity. seed.sql cố ý báo lỗi nếu bảng đã tồn tại; chạy một lần trên DB mới. Đây là dữ liệu giả. Không cần mở inbound cổng 5432; chương trình kết nối PostgreSQL nội bộ bằng OS user postgres.

Kiểm tra hai file config đã có trong bộ mã:

```bash
sudo cat /opt/cloudbackup/demo-config/app.conf
sudo cat /opt/cloudbackup/demo-config/services/worker.conf
sudo find /opt/cloudbackup/demo-config -type f -exec sha256sum {} \;
```

Kỳ vọng app.conf có version=1 và worker.conf có enabled=true. Không thêm mật khẩu, token hoặc private key vào thư mục này. Bộ mã chỉ cho phép thư mục/file thông thường, từ chối symlink và special file.

Giải thích: cat chỉ đọc nội dung file; find ... sha256sum tính dấu kiểm tra nội dung mỗi file. SHA-256 giống dấu vân tay của file: đổi nội dung thì giá trị kiểm tra thường đổi. Việc in được checksum mới chỉ ghi nhận bản hiện tại; cần so sánh với bản khôi phục để kiểm tra toàn vẹn.

Chụp một ảnh truy vấn DB và một ảnh config; lưu bằng chứng ngày 1. Báo Dương rằng DB mẫu và dữ liệu đã sẵn sàng để restore thủ công.

---PAGE---
## 5 Làm một lần backup và restore thủ công
Chạy trên EC2 bằng Bash. Các biến trong đoạn này tồn tại trong terminal hiện tại; nếu mở terminal mới phải khai báo lại.

```bash
MANUAL_DIR="$HOME/manual-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$MANUAL_DIR"
sudo -u postgres pg_dump -w -Fc -d cloud_backup_demo > "$MANUAL_DIR/database.dump"
echo "PG_DUMP_EXIT=$?"
tar -czf "$MANUAL_DIR/configuration.tar.gz" -C /opt/cloudbackup demo-config
echo "TAR_EXIT=$?"
sha256sum "$MANUAL_DIR/database.dump" "$MANUAL_DIR/configuration.tar.gz"
pg_restore --list "$MANUAL_DIR/database.dump" | head -n 12
tar -tzf "$MANUAL_DIR/configuration.tar.gz"
```

Mục đích của bài thủ công: chứng minh các công cụ DB và nén file hoạt động trước khi thêm Python/S3. MANUAL_DIR tạo tên thư mục theo giờ UTC; pg_dump -Fc xuất DB theo định dạng custom; -w không hỏi mật khẩu; > ghi dữ liệu đầu ra vào file. tar -czf gom và nén thư mục cấu hình; -C chọn thư mục gốc. pg_restore --list xem mục lục dump; tar -tzf xem danh sách file nén [1][2].

Kiểm tra kích thước trước khi restore:

```bash
ls -lh "$MANUAL_DIR/database.dump" "$MANUAL_DIR/configuration.tar.gz"
```

Đạt khi cả hai file có dung lượng lớn hơn 0, PG_DUMP_EXIT=0, TAR_EXIT=0 và mục lục tar có hai file config. File tồn tại nhưng dump 0 byte là chưa đạt.

---PAGE---
## 5 (tiếp) Khôi phục vào DB thử riêng

Hai exit code cần bằng 0; dump khác 0 byte. Pipeline có head chỉ để xem danh sách, không dùng exit code của pipeline đó thay cho mã thoát pg_dump.

```bash
MANUAL_DB="cloud_restore_manual_$(date -u +%Y%m%d%H%M%S)"
sudo -u postgres createdb -T template0 "$MANUAL_DB"
sudo -u postgres pg_restore -w --exit-on-error --no-owner --no-acl -d "$MANUAL_DB" < "$MANUAL_DIR/database.dump"
echo "RESTORE_EXIT=$?"
sudo -u postgres psql -X -d "$MANUAL_DB" -c 'SELECT COUNT(*) FROM demo_inventory;'
mkdir "$MANUAL_DIR/recovered"
tar -xzf "$MANUAL_DIR/configuration.tar.gz" -C "$MANUAL_DIR/recovered"
diff -r /opt/cloudbackup/demo-config "$MANUAL_DIR/recovered/demo-config"
```

Giải thích: MANUAL_DB đặt tên database thử theo thời gian; createdb -T template0 tạo DB đích mới. pg_restore đọc dump qua dấu <, khôi phục vào DB thử; --exit-on-error dừng khi có lỗi; --no-owner và --no-acl bỏ khôi phục chủ sở hữu/quyền gốc trong bài lab [2]. tar -xzf giải nén config vào thư mục recovered; diff -r so sánh nội dung hai cây thư mục. Không có lệnh xóa hoặc ghi đè database cloud_backup_demo trong bài này.

Ngay sau diff chạy:

```bash
echo "CONFIG_DIFF_EXIT=$?"
```

Đạt khi CONFIG_DIFF_EXIT=0 và diff không in khác biệt. Exit 1 nghĩa là nội dung khác nhau; exit lớn hơn 1 thường là lỗi đọc/so sánh, không được coi là khác biệt dữ liệu thông thường.

Kỳ vọng restore exit 0, count 100, diff không in khác biệt. Dùng stdin để postgres không phải đi xuyên thư mục home của ec2-user đọc file. Gói tar thủ công này do chính bạn vừa tạo; bước restore tự động sau này có thêm kiểm tra đường dẫn an toàn.

Đoạn thủ công dùng tên thư mục demo-config trong archive. Chương trình tự động dùng tên config. Không trộn file thủ công vào phiên tự động; chúng chỉ giúp bạn hiểu pg_dump, tar và pg_restore đang làm gì.

Đếm 100 dòng chưa đủ để chứng minh nội dung khôi phục đúng. Khi không có ai sửa DB trong lúc test, xuất toàn bộ bảng gốc và bảng khôi phục theo cùng thứ tự rồi so sánh:

```bash
sudo -u postgres psql -X -v ON_ERROR_STOP=1 -d cloud_backup_demo -c 'COPY (SELECT * FROM public.demo_inventory ORDER BY item_id) TO STDOUT WITH CSV HEADER' > "$MANUAL_DIR/original.csv"
echo "EXPORT_ORIGINAL_EXIT=$?"
sudo -u postgres psql -X -v ON_ERROR_STOP=1 -d "$MANUAL_DB" -c 'COPY (SELECT * FROM public.demo_inventory ORDER BY item_id) TO STDOUT WITH CSV HEADER' > "$MANUAL_DIR/restored.csv"
echo "EXPORT_RESTORED_EXIT=$?"
diff -u "$MANUAL_DIR/original.csv" "$MANUAL_DIR/restored.csv"
echo "DATA_DIFF_EXIT=$?"
```

Cả hai EXPORT phải bằng 0 trước khi xét DATA_DIFF_EXIT=0. Nếu xuất cả hai file thất bại và đều rỗng, diff vẫn có thể bằng 0, nên không bỏ qua kiểm tra EXPORT. Bài này đối chiếu nội dung bảng demo; bài restore tự động của Dương còn kiểm tra schema, constraints, sequence và checksum.

Đến đây đã chứng minh dump có thể khôi phục. Bước sau mới đưa quy trình này vào Python và lưu theo phiên trên S3. Không cần chờ hoàn thành SMS để làm tiếp backup.

---PAGE---
## 6 Cấu hình bucket và chạy backup thật
Tạo file cấu hình lần đầu; lệnh install ghi đè nếu đã tồn tại, nên kiểm tra trước:

```bash
sudo test -e /etc/cloudbackup.json && echo 'Config already exists: inspect before changing'
```

Nếu chưa có file:

```bash
sudo install -m 600 /opt/cloudbackup/config.example.json /etc/cloudbackup.json
sudo nano /etc/cloudbackup.json
```

Trong nano, thay giá trị THAY_TEN_BUCKET thành cloud-backup-07-unique, giữ aws_region là ap-southeast-1. Giữ s3_prefix=backups để khớp quyền IAM. Để sns_topic_arn rỗng lúc đầu; Hưng điền sau. Giữ nguyên database, config_dir và local_backup_dir nếu làm đúng các bước trên. File phải là JSON hợp lệ, không có comment hoặc dấu phẩy cuối.

Cách dùng nano: di chuyển bằng phím mũi tên, sửa đúng phần giá trị trong dấu nháy kép; Ctrl+O rồi Enter để lưu; Ctrl+X để thoát. Nếu nano chưa cài, chạy sudo dnf install -y nano rồi mở lại. Ba dòng cần đối chiếu trong JSON là:

```json
"s3_bucket": "cloud-backup-07-unique",
"s3_prefix": "backups",
"aws_region": "ap-southeast-1",
```

Đây chỉ là ba dòng trích từ file, không thay toàn bộ JSON bằng ba dòng này. Không điền access key hoặc secret key; chương trình dùng role gắn trên EC2.

---PAGE---
## 6 (tiếp) Chạy và đọc kết quả backup
json.tool kiểm tra cú pháp JSON; thành công sẽ in cấu hình đẹp hơn, nhưng chưa chứng minh tên bucket hoặc quyền IAM đúng. Nếu báo lỗi ở dòng/cột nào, sửa cấu hình trước rồi kiểm tra lại. Chỉ chạy backup.py khi JSON hợp lệ.

```bash
sudo /opt/cloudbackup/.venv/bin/python -m json.tool /etc/cloudbackup.json
sudo /opt/cloudbackup/.venv/bin/python /opt/cloudbackup/src/backup.py --config /etc/cloudbackup.json
echo "BACKUP_EXIT=$?"
sudo tail -n 10 /var/backups/cloudbackup/backup.log
sudo /opt/cloudbackup/.venv/bin/python /opt/cloudbackup/src/list_backups.py
```

Giải thích: backup.py thực hiện dump DB, nén config, tính checksum và upload lên S3; BACKUP_EXIT ghi lại kết quả ngay sau lệnh. tail -n 10 xem 10 dòng log cuối; list_backups.py liệt kê các phiên trên S3. Mỗi lần chạy backup thành công tạo một RUN_ID mới, không phải cập nhật nội dung phiên trước.

Nếu backup lỗi, dừng xem log trước; list_backups có thể vẫn hiển thị phiên tốt cũ. Đối chiếu đúng RUN_ID của lần vừa chạy, không lấy phiên cũ làm bằng chứng lần mới thành công.

Kỳ vọng exit 0, log BACKUP_SUCCESS, dòng RUN_ID=2026...-........, danh sách có SUCCESS_MARKER. Sao chép RUN_ID nguyên vẹn, không gõ dấu ngoặc nhọn hay chữ RUN_ID= vào tham số restore.

Mở S3 Console → bucket → backups → RUN_ID. Phải có đúng 4 object dữ liệu/metadata. Mở manifest.json: kiểm tra database, started_at, files, config_files và demo_baseline. SUCCESS.json ghi completed_at và checksum manifest; nó được upload cuối cùng.

```bash
sudo cat /var/backups/cloudbackup/last_success.json
sudo du -sh /var/backups/cloudbackup
```

Ý nghĩa bốn object: database.dump chứa DB; configuration.tar.gz chứa file config; manifest.json lưu thông tin phiên và checksum; SUCCESS.json đánh dấu bước ghi dữ liệu của phiên đã hoàn tất. SUCCESS_MARKER chỉ là kết quả nhìn thấy các object bắt buộc, chưa phải kết quả test restore.

last_success.json phải tham chiếu phiên vừa thành công. du -sh cho biết tổng dung lượng local; nó không kiểm tra dung lượng S3. Chụp một ảnh BACKUP_EXIT=0/RUN_ID, một ảnh danh sách bốn object đúng thư mục trên S3, và lưu log phiên tương ứng.

State ghi thời gian của phiên thành công mới nhất. Nếu một tác vụ lỗi, state này không được đổi. HeadObject trong backup chỉ kiểm tra size; restore sẽ tải lại và xác minh SHA-256. Giao RUN_ID cho Dương ngay khi có phiên đầu tiên.

---PAGE---
## 7 Thử lỗi và hiểu mã thoát
Mục đích: giả lập tên DB sai để kiểm tra chương trình báo lỗi, trả mã thất bại và không ghi nhận một phiên tốt giả. Chỉ làm sau khi phần 6 đã có ít nhất một backup thành công. Báo Đức tạm thời chưa chạy cron trong lúc kiểm tra để tác vụ khác không thay đổi state giữa hai lần đọc.

Tạo file cấu hình lỗi riêng. Tool từ chối ghi đè file đã có; nếu đã tạo trước đó thì dùng lại file sau khi xem nội dung.

```bash
sudo /opt/cloudbackup/.venv/bin/python /opt/cloudbackup/tools/make_error_config.py --kind db --out /etc/cloudbackup-error-db.json
sudo cat /var/backups/cloudbackup/last_success.json
sudo /opt/cloudbackup/.venv/bin/python /opt/cloudbackup/src/backup.py --config /etc/cloudbackup-error-db.json
echo "EXPECTED_1=$?"
sudo cat /var/backups/cloudbackup/last_success.json
sudo tail -n 12 /var/backups/cloudbackup/backup.log
```

Giải thích: make_error_config.py sao chép cấu hình chính sang file riêng rồi đổi tên DB thành nhom7_database_does_not_exist. Cấu hình chính vẫn giữ nguyên. Tool cũng đặt update_state=false; do đó bài test này kiểm tra luồng báo lỗi và sự giữ nguyên state trong chế độ thử, không tự nó chứng minh mọi trường hợp lỗi ở cấu hình production đều giữ nguyên state.

Nếu tool báo FileExistsError thì file thử đã tồn tại: xem nội dung hoặc dùng tên mới và thay tên đó đồng bộ trong lệnh backup; không xóa cấu hình chính. So sánh RUN_ID/thời gian trong last_success.json trước và sau: phải giống nhau. Mã EXPECTED_1=1 là kết quả đúng riêng cho bài cố tình gây lỗi.

Kỳ vọng BACKUP_FAILED, exit 1 và state vẫn chỉ phiên tốt cũ. Ban đầu log có NOTIFICATION_NOT_CONFIGURED là bình thường. Khi Hưng đã cấu hình topic, tạo lại bản config lỗi với tên file mới để nhận topic mới, rồi kiểm tra NOTIFICATION_PUBLISHED và SMS thật. Cấu hình lỗi được sao chép tại lúc tạo, không tự cập nhật theo config chính.

Sau bài thử lỗi, chạy lại cấu hình chính để chứng minh hệ thống vẫn hoạt động:

```bash
sudo /opt/cloudbackup/.venv/bin/python /opt/cloudbackup/src/backup.py --config /etc/cloudbackup.json
echo "RECOVERY_BACKUP_EXIT=$?"
```

Kỳ vọng RECOVERY_BACKUP_EXIT=0 và RUN_ID mới. Gửi RUN_ID tốt mới này cho Dương; không gửi tên phiên lỗi. Nếu vẫn lỗi, dừng để xem backup.log, không cài cron chạy lặp lỗi.

| Exit | Ý nghĩa | Cách xử lý |
| --- | --- | --- |
| 0 | Backup đã commit trên S3 | Chuyển Dương test restore |
| 1 | Backup hoặc startup lỗi | Xem step/error; không coi phiên này là tốt |
| 2 | S3 đã commit nhưng cập nhật state lỗi | Kiểm tra quyền/dung lượng local; restore phiên S3 để xác nhận |
| 75 | Có tác vụ khác giữ khóa | Không chạy chồng; xem tác vụ đang chạy |

Nếu nhập sai JSON hoặc thiếu thư viện, lỗi xảy ra trước khi có cấu hình hợp lệ; chương trình không bảo đảm tự gửi SNS trong trường hợp này. Cron log và CloudWatch missing-data/age là lớp phát hiện bổ sung.

Trong src/backup.py, đọc theo thứ tự: LOCK → DATABASE_BASELINE → PG_DUMP → CONFIG_ARCHIVE → S3_UPLOAD → COMMIT → STATE. Hãy hiểu vì sao SUCCESS ghi cuối và last_success chỉ cập nhật sau commit. Mã dùng role của EC2 qua boto3, không có access key hard-code.

Không thay đổi DB/config khi đang backup. Kiểm tra baseline trước/sau có thể phát hiện thay đổi, nhưng không biến DB và filesystem thành một snapshot giao dịch chung. Bộ demo tự đối chiếu bảng demo_inventory; nếu đổi tên/schema bảng, cần đổi phần snapshot tương ứng.

---PAGE---
## 8 Lỗi thường gặp và bàn giao
| Hiện tượng | Kiểm tra và sửa |
| --- | --- |
| No module named boto3 | Dùng đúng /opt/cloudbackup/.venv/bin/python; cài requirements bằng venv |
| Peer authentication failed | Script phải chạy sudo; DB commands chạy OS user postgres |
| relation demo_inventory does not exist | Chưa seed hoặc sai database trong JSON |
| Permission denied với file dump | Truyền dump qua stdin như mẫu; không chmod 777 |
| AccessDenied S3 | STS đúng role, prefix backups, PutObject/GetObject/ListBucket; xem bucket policy |
| Command timeout | Kiểm tra DB/service và log; tăng timeout có lý do, không bỏ giới hạn |
| Không có SUCCESS trên S3 | Phiên chưa hoàn tất; xem log và FAILED.json local |
| CloudWatch chưa thấy log | Là phần Hưng cấu hình; local backup vẫn có thể chạy trước |

Chạy test offline trên chính EC2 để bổ sung hai test Linux chưa chạy được trên máy soạn tài liệu:

```bash
cd /opt/cloudbackup
sudo /opt/cloudbackup/.venv/bin/python -m unittest discover -s tests -v
```

Các test này mô phỏng AWS/DB, không gửi SMS và không thay thế bài chạy thật. Trên Linux dự kiến 18 test đều chạy; nếu có lỗi lưu nguyên traceback và sửa trước khi nộp.

---PAGE---
## 9 Checklist nghiệm thu phần Hoàng
Không đánh dấu đạt chỉ vì lệnh đã được dán vào terminal. Đánh dấu theo kết quả thực tế; lưu ảnh/log kèm RUN_ID và thời gian chạy.

| Bài kiểm tra | Điều kiện đạt |
| --- | --- |
| Danh tính AWS | Account đúng, STS bằng sudo dùng role EC2 |
| Dữ liệu đầu vào | DB mẫu 100 dòng, 5 dòng đầu đúng, đủ hai config |
| Backup thủ công | PG_DUMP_EXIT=0, TAR_EXIT=0, hai file khác 0 byte |
| Restore thủ công | RESTORE_EXIT=0, COUNT=100 |
| Nội dung bảng | Hai EXPORT exit 0 và DATA_DIFF_EXIT=0 |
| Nội dung config | CONFIG_DIFF_EXIT=0, không có khác biệt |
| Backup S3 | BACKUP_EXIT=0, RUN_ID mới, đủ bốn object đúng phiên |
| State và log | BACKUP_SUCCESS cùng RUN_ID, last_success khớp phiên |
| Bài lỗi DB | EXPECTED_1=1, BACKUP_FAILED, state trước/sau không đổi |
| Phục hồi sau thử lỗi | Cấu hình chính chạy lại exit 0, có phiên tốt mới |
| Unit test | Đọc tổng số test, không có FAILED/ERROR ngoài kết quả kỳ vọng |

Phần của Hoàng hoàn tất khi các mục trên đạt và đã giao RUN_ID cho Dương. Project còn cần Dương tải bản trên S3 về restore và xác minh; Đức kiểm tra lịch tự động; Hưng kiểm tra log, metric và cảnh báo. Bài thủ công local chưa chứng minh file tải lại từ S3 khôi phục được.

Đặt tên ảnh rõ ràng, ví dụ 01-sts-role.png, 02-db-100.png, 03-manual-restore.png, 04-s3-run.png, 05-error-test.png. Ảnh có thông tin thực tế; không thay ảnh chạy thật bằng phần kết quả kỳ vọng trong hướng dẫn.

## Nếu đóng terminal giữa chừng
File và dịch vụ trên EC2 vẫn còn, nhưng các biến MANUAL_DIR/MANUAL_DB trong terminal cũ không tự có trong phiên mới. Không chạy lại initdb hoặc seed chỉ vì mở terminal mới. Với bài thủ công, có thể bắt đầu lại phần 5 để tạo một thư mục và DB thử mới; không xóa DB gốc. Với backup tự động, dùng đường dẫn tuyệt đối như tài liệu nên có thể chạy từ thư mục bất kỳ.

Nếu bị kẹt: gửi số bước, câu lệnh vừa chạy và toàn bộ đoạn lỗi; ví dụ “Bước 6, backup.py, BACKUP_EXIT=1, log step=S3_UPLOAD...”. Không gửi file PEM hoặc credential. Chưa có output thì ghi là chưa kiểm tra, không ghi đã đạt.


## Bàn giao cho nhóm
Gửi Region, bucket, tên role, đường dẫn config, RUN_ID tốt, phiên bản PostgreSQL/Python, requirements.lock.txt và log đã che thông tin cần che. Không gửi PEM, credentials hoặc dữ liệu nhạy cảm. Dương nhận RUN_ID để restore; Đức dùng lệnh backup đã đạt để cài cron; Hưng nhận log path và namespace để cấu hình CloudWatch.

## Nếu EC2 thực tế là Ubuntu
Dùng user ubuntu và đường dẫn SCP /home/ubuntu/. Cài gói bằng lệnh sau thay cho dnf; các đường dẫn /opt/cloudbackup, /etc/cloudbackup.json và /var/backups/cloudbackup giữ nguyên:

```bash
sudo apt-get update
sudo apt-get install -y postgresql postgresql-client python3-venv python3-pip cron logrotate
sudo systemctl enable --now postgresql
```

Ubuntu thường tạo cluster trong lúc cài gói; không chạy postgresql-setup. Giữ client/server cùng major version do kho Ubuntu cung cấp, không ép 15 khi hệ thống đã có phiên bản phù hợp. Đức dùng service cron thay crond. Hưng cài CloudWatch Agent bằng gói Ubuntu đúng kiến trúc theo nguồn AWS [3].

## Nguồn kỹ thuật
[1] PostgreSQL pg_dump: https://www.postgresql.org/docs/15/app-pgdump.html
[2] PostgreSQL pg_restore: https://www.postgresql.org/docs/15/app-pgrestore.html
[3] CloudWatch Agent download: https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/download-CloudWatch-Agent-on-EC2-Instance-commandline-first.html
