"""Create a deliberately incomplete or corrupt S3 LAB fixture in a new run prefix."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from common import LabError, aws, read_config, require_root, run_id, validate_run

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("--config", default="/etc/cloudbackup.json")
p.add_argument("--source-run", required=True)
p.add_argument("--kind", choices=["incomplete", "corrupt"], required=True)
a = p.parse_args()
require_root()
c = read_config(a.config)
validate_run(a.source_run)
s3 = aws(c, "s3")
source = c["s3_prefix"] + "/" + a.source_run + "/"
# New fixture is isolated from good runs. Never change source data.
rid = run_id()
target = c["s3_prefix"] + "/" + rid + "/"

def read(name):
    r = s3.get_object(Bucket=c["s3_bucket"], Key=source + name)
    try:
        if r["ContentLength"] > c["max_backup_bytes"]:
            raise LabError("Fixture input exceeds lab size cap")
        return r["Body"].read(c["max_backup_bytes"] + 1)
    finally:
        r["Body"].close()

manifest = json.loads(read("manifest.json"))
success = json.loads(read("SUCCESS.json"))
if manifest["run_id"] != a.source_run or success["run_id"] != a.source_run:
    raise LabError("Source markers do not match")
manifest["run_id"] = rid
manifest["test_fixture"] = a.kind
manifest_bytes = json.dumps(manifest, indent=2).encode()
import hashlib
success["run_id"] = rid
success["manifest_sha256"] = hashlib.sha256(manifest_bytes).hexdigest()
success["test_fixture"] = a.kind
for name in ("database.dump", "configuration.tar.gz"):
    data = read(name)
    if a.kind == "corrupt" and name == "database.dump":
        if not data:
            raise LabError("Empty source dump")
        data = bytes([data[0] ^ 1]) + data[1:]
    s3.put_object(Bucket=c["s3_bucket"], Key=target + name, Body=data)
s3.put_object(Bucket=c["s3_bucket"], Key=target + "manifest.json", Body=manifest_bytes)
if a.kind == "corrupt":
    s3.put_object(Bucket=c["s3_bucket"], Key=target + "SUCCESS.json", Body=json.dumps(success).encode())
print("FIXTURE_RUN_ID=" + rid)
print("Expected restore result: FAIL. Main state and original run are unchanged.")
