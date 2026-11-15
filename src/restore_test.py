"""Verify S3 checksums; restore only into a new cloud_restore_ database."""
import argparse
import json
from pathlib import Path
import sys
import time
import uuid
from common import (LabError, atomic_json, aws, command, config_inventory, download,
                    log, pg_args, read_config, require_root, safe_extract, sha,
                    snapshot, utc, validate_run)


def fetch_verified(c, rid, work):
    s3 = aws(c, "s3")
    prefix = f'{c["s3_prefix"]}/{rid}/'
    for name in ("SUCCESS.json", "manifest.json"):
        download(s3, c["s3_bucket"], prefix + name, work / name, 1024 * 1024)
    success = json.loads((work / "SUCCESS.json").read_text(encoding="utf-8"))
    manifest = json.loads((work / "manifest.json").read_text(encoding="utf-8"))
    if (success.get("schema_version") != 1 or manifest.get("schema_version") != 1 or
            success.get("run_id") != rid or manifest.get("run_id") != rid or
            success.get("manifest_sha256") != sha(work / "manifest.json")):
        raise LabError("Invalid SUCCESS or manifest")
    files = manifest.get("files", [])
    if len(files) != 2 or {x.get("name") for x in files} != {"database.dump", "configuration.tar.gz"}:
        raise LabError("Manifest must contain exactly the two expected data files")
    for item in files:
        size = item.get("size")
        if not isinstance(size, int) or not 0 < size <= c["max_backup_bytes"]:
            raise LabError("Invalid size in manifest")
        target = work / item["name"]
        download(s3, c["s3_bucket"], prefix + item["name"], target, c["max_backup_bytes"])
        if target.stat().st_size != size or sha(target) != item["sha256"]:
            raise LabError("Checksum or size mismatch: " + item["name"])
    return manifest


def execute(c, rid, verify_only=False):
    validate_run(rid)
    started = time.monotonic()
    work = Path(c["local_backup_dir"]) / "restore" / (rid + "-" + uuid.uuid4().hex[:8])
    work.mkdir(parents=True)
    db = None
    try:
        manifest = fetch_verified(c, rid, work)
        recovered = work / "recovered"
        safe_extract(work / "configuration.tar.gz", recovered, c["max_backup_bytes"])
        if config_inventory(recovered / "config") != manifest["config_files"]:
            raise LabError("Restored config inventory mismatch")
        if not verify_only:
            db = "cloud_restore_" + uuid.uuid4().hex[:16]
            if db == c["database"] or db == manifest.get("database"):
                raise LabError("Refusing source database")
            # createdb fails if this random target already exists. Never use --clean/-C.
            command(pg_args("createdb", "-T", "template0", db), c["command_timeout_seconds"])
            with (work / "database.dump").open("rb") as inp:
                command(pg_args("pg_restore", "-w", "--exit-on-error", "--no-owner", "--no-acl", "-d", db),
                        c["command_timeout_seconds"], stdin=inp)
            if snapshot(c, db) != manifest["demo_baseline"]:
                raise LabError("Restored demo rows/schema/constraints/sequence mismatch")
        result = {"run_id": rid, "utc": utc(), "status": "VERIFIED_ONLY" if verify_only else "RESTORE_PASS",
                  "database": db, "config_dir": str(recovered / "config"),
                  "seconds": round(time.monotonic() - started, 3)}
        atomic_json(work / "result.json", result)
        log(c, result["status"], **{k: v for k, v in result.items() if k != "status"})
        print("RESULT=" + str(work / "result.json"))
        if db:
            print("RESTORE_DB=" + db)
        print("RESTORED_CONFIG=" + str(recovered / "config"))
        return 0
    except Exception as exc:
        log(c, "RESTORE_FAILED", run_id=rid, database=db, error_type=type(exc).__name__, error=str(exc)[:1800])
        atomic_json(work / "result.json", {"status": "FAILED", "database": db, "error": str(exc)[:1800]})
        # Leave failed test DB/staging for inspection. Never delete a database automatically.
        return 1


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", default="/etc/cloudbackup.json")
    p.add_argument("--run-id", required=True)
    p.add_argument("--verify-only", action="store_true", help="Check files and config without creating a DB")
    args = p.parse_args()
    try:
        require_root()
        return execute(read_config(args.config), args.run_id, args.verify_only)
    except Exception as exc:
        print("RESTORE_ERROR: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
