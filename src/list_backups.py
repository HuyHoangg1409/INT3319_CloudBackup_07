"""List S3 run markers. SUCCESS_MARKER is not a completed restore test."""
import argparse
import sys
from common import RUN_RE, aws, read_config


def execute(c):
    s3 = aws(c, "s3")
    prefix = c["s3_prefix"] + "/"
    runs = {}
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=c["s3_bucket"], Prefix=prefix):
        for obj in page.get("Contents", []):
            rel = obj["Key"][len(prefix):].split("/")
            if len(rel) != 2 or not RUN_RE.fullmatch(rel[0]):
                continue
            record = runs.setdefault(rel[0], {"names": set(), "bytes": 0})
            record["names"].add(rel[1])
            record["bytes"] += obj["Size"]
    print("RUN_ID\tSTATUS\tBYTES")
    required = {"database.dump", "configuration.tar.gz", "manifest.json", "SUCCESS.json"}
    for rid, record in sorted(runs.items(), reverse=True):
        status = "SUCCESS_MARKER" if required <= record["names"] else "INCOMPLETE"
        print(f'{rid}\t{status}\t{record["bytes"]}')
    if not runs:
        print("No backup runs found. Week-1 text files are ignored.")
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", default="/etc/cloudbackup.json")
    a = p.parse_args()
    try:
        sys.exit(execute(read_config(a.config)))
    except Exception as exc:
        print("LIST_ERROR: " + str(exc), file=sys.stderr)
        sys.exit(1)
