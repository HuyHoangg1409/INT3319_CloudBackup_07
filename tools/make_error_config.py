"""Create a separate lab failure config; never edits the main config/state."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from common import read_config
p = argparse.ArgumentParser(description=__doc__)
p.add_argument("--config", default="/etc/cloudbackup.json")
p.add_argument("--kind", choices=["db", "s3"], required=True)
p.add_argument("--out", required=True)
a = p.parse_args()
if Path(a.out).resolve() == Path(a.config).resolve():
    p.error("Output cannot overwrite the main config")
c = read_config(a.config)
c["update_state"] = False
if a.kind == "db":
    c["database"] = "nhom7_database_does_not_exist"
else:
    c["s3_prefix"] = "denied-nhom7-test"
target = Path(a.out)
with target.open("x", encoding="utf-8") as f:
    json.dump(c, f, indent=2)
target.chmod(0o600)
print(str(target))
