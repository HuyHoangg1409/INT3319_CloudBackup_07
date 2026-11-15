"""Generate JSON locally. Does NOT create/change AWS resources."""
import argparse
import json
from pathlib import Path
import re
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from common import read_config

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("--config", default="/etc/cloudbackup.json")
p.add_argument("--account-id", required=True)
p.add_argument("--out", default="/opt/cloudbackup/generated")
a = p.parse_args()
if not re.fullmatch(r"\d{12}", a.account_id):
    p.error("account-id must be exactly 12 digits")
c = read_config(a.config)
if not c["sns_topic_arn"].startswith(f'arn:aws:sns:{c["aws_region"]}:{a.account_id}:'):
    p.error("Set the actual SNS topic ARN in config first")
out = Path(a.out)
out.mkdir(parents=True, exist_ok=True)
bucket = c["s3_bucket"]
prefix = c["s3_prefix"]
region = c["aws_region"]
account = a.account_id
group = f"arn:aws:logs:{region}:{account}:log-group:/cloudbackup/nhom7"
stream = group + ":log-stream:*"
alarm_name = "cloudbackup-nhom7-age"
alarm_arn = f"arn:aws:cloudwatch:{region}:{account}:alarm:{alarm_name}"
role_policy = {"Version": "2012-10-17", "Statement": [
    {"Sid": "ListBackupPrefix", "Effect": "Allow", "Action": "s3:ListBucket",
     "Resource": f"arn:aws:s3:::{bucket}", "Condition": {"StringLike": {"s3:prefix": [prefix, prefix + "/*"]}}},
    {"Sid": "BackupObjects", "Effect": "Allow", "Action": ["s3:PutObject", "s3:GetObject"],
     "Resource": f"arn:aws:s3:::{bucket}/{prefix}/*"},
    {"Sid": "PublishAlerts", "Effect": "Allow", "Action": "sns:Publish", "Resource": c["sns_topic_arn"]},
    {"Sid": "PublishAge", "Effect": "Allow", "Action": "cloudwatch:PutMetricData", "Resource": "*",
     "Condition": {"StringEquals": {"cloudwatch:namespace": c["namespace"]}}},
    {"Sid": "InspectLogStreams", "Effect": "Allow", "Action": "logs:DescribeLogStreams", "Resource": group},
    {"Sid": "WriteLogs", "Effect": "Allow", "Action": ["logs:CreateLogStream", "logs:PutLogEvents"], "Resource": stream},
    {"Sid": "DescribeGroups", "Effect": "Allow", "Action": "logs:DescribeLogGroups", "Resource": "*"}
]}
topic_statement = {"Sid": "CloudBackupAlarm", "Effect": "Allow", "Principal": {"Service": "cloudwatch.amazonaws.com"},
    "Action": "sns:Publish", "Resource": c["sns_topic_arn"], "Condition": {
        "StringEquals": {"aws:SourceAccount": account}, "ArnEquals": {"aws:SourceArn": alarm_arn}}}
alarm = {"AlarmName": alarm_name, "AlarmDescription": "Backup overdue or monitoring signal absent. Investigate logs.",
    "ActionsEnabled": True, "AlarmActions": [c["sns_topic_arn"]], "OKActions": [c["sns_topic_arn"]],
    "Namespace": c["namespace"], "MetricName": "BackupAgeSeconds", "Statistic": "Maximum", "Unit": "Seconds",
    "Dimensions": [{"Name": "Project", "Value": c["project"]}, {"Name": "Environment", "Value": c["environment"]}],
    "Period": 60, "EvaluationPeriods": 2, "DatapointsToAlarm": 2, "Threshold": c["overdue_seconds"],
    "ComparisonOperator": "GreaterThanThreshold", "TreatMissingData": "breaching"}
for name, obj in [("ec2-runtime-policy.json", role_policy), ("topic-alarm-statement.json", topic_statement), ("alarm.json", alarm)]:
    (out / name).write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")
print("Generated local JSON files in " + str(out))
