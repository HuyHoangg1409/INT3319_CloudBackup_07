# Biên bản nghiệm thu để nhóm tự điền

Ngày giờ: ... | Commit/tag: ... | OS: ... | PostgreSQL: ... | Python: ...
Region: ... | Bucket: ... | Instance: ... | Người chạy: ... | Người kiểm tra: ...

Không ghi secret, private key hoặc access key. Trạng thái hợp lệ: CHUA_CHAY, PASS, FAIL, BLOCKED. Cột kết quả thực tế bắt buộc có dẫn chứng khi ghi PASS.

| Mã | Bài kiểm thử | Trạng thái | Kết quả thực tế và minh chứng |
| --- | --- | --- | --- |
| T01 | Backup thành công đủ 4 object | CHUA_CHAY | |
| T02 | Restore DB/config đúng baseline | CHUA_CHAY | |
| T03 | Restore chọn phiên A sau khi đã tạo B | CHUA_CHAY | |
| T04 | DB sai, exit 1, state giữ nguyên, SNS | CHUA_CHAY | |
| T05 | S3 denied, không SUCCESS, SNS | CHUA_CHAY | |
| T06 | Dump đổi một byte, restore từ chối | CHUA_CHAY | |
| T07 | Thiếu SUCCESS, restore từ chối | CHUA_CHAY | |
| T08 | Hai phiên backup từ cron | CHUA_CHAY | |
| T09a | Giữ khóa, lần thứ hai exit 75 | CHUA_CHAY | |
| T09b | Linux timeout test đạt | CHUA_CHAY | |
| T10 | Tắt cron backup, heartbeat còn chạy, alarm | CHUA_CHAY | |
| T11 | Stop EC2, missing metric gây alarm | CHUA_CHAY | |
| T12 | Hồi phục, backup tốt, alarm OK | CHUA_CHAY | |
| T13a | Log trên CloudWatch đúng run_id | CHUA_CHAY | |
| T13b | SMS từ lỗi backup đến thật | CHUA_CHAY | |
| T13c | SMS từ CloudWatch Alarm đến thật | CHUA_CHAY | |

## Kết quả đo restore

| Lần | RUN_ID | Dòng dữ liệu | Dump bytes | Seconds trong result.json | Kết luận |
| --- | --- | --- | --- | --- | --- |
| 1 | | | | | |
| 2 | | | | | |
| 3 | | | | | |

## Độ trễ cảnh báo

| Tình huống | Metric tốt cuối | ALARM lúc | Email lúc | SMS lúc | Ghi chú |
| --- | --- | --- | --- | --- | --- |
| Tắt cron | | | | | |
| Stop EC2 | | | | | |

## Lỗi còn lại và giới hạn

Mô tả lỗi: ... | Nguyên nhân đã xác minh: ... | Người xử lý: ... | Hạn xử lý: ...
SMS sandbox/registration: ... | Email: ... | SMS: ...
Lịch sau demo: ... | Threshold alarm: ... | Kế hoạch giữ/dọn dữ liệu: ...

## Điều kiện đóng gói

- README chạy lại được với thông số thật đã che phần không nên công khai.
- requirements.lock.txt lấy từ EC2 thực tế và commit/tag bản nộp.
- Có video, ảnh/log, result.json và RUN_ID tốt để demo lại.
- Không có PEM, AWS credential, mật khẩu hoặc dump dữ liệu người thật.
- Trạng thái trong báo cáo khớp test report; không gọi tính năng chưa đạt là đã hoàn thành.
