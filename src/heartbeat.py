"""Publish backup age independently from the backup cron job."""
import argparse
import json
from pathlib import Path
import sys
import time
from common import aws, backup_age, log, read_config, require_root


def execute(c):
    try:
        try:
            state = json.loads((Path(c["local_backup_dir"]) / "last_success.json").read_text())
        except (OSError, ValueError):
            state = {}
        age, status = backup_age(state, time.time(), c["overdue_seconds"])
        aws(c, "cloudwatch").put_metric_data(Namespace=c["namespace"], MetricData=[{
            "MetricName": "BackupAgeSeconds", "Unit": "Seconds", "Value": age,
            "Dimensions": [{"Name": "Project", "Value": c["project"]},
                           {"Name": "Environment", "Value": c["environment"]}]}])
        # Separate log keeps backup.log useful and avoids an entry every minute there.
        print(f"HEARTBEAT_OK age_seconds={age:.1f} state={status}", flush=True)
        return 0
    except Exception as exc:
        log(c, "HEARTBEAT_FAILED", error_type=type(exc).__name__, error=str(exc)[:1000])
        return 1


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", default="/etc/cloudbackup.json")
    a = p.parse_args()
    try:
        require_root()
        sys.exit(execute(read_config(a.config)))
    except Exception as exc:
        print("HEARTBEAT_ERROR: " + str(exc), file=sys.stderr)
        sys.exit(1)
