"""Full logical PostgreSQL + config backup for the Nhom7 lab."""
import argparse
import json
from pathlib import Path
import sys
import tarfile
import time
from common import (BusyError, LabError, atomic_json, aws, command, config_inventory,
                    lock, log, notify, pg_args, query, read_config, require_root,
                    run_id, sha, snapshot, utc)


def execute(c):
    rid = run_id()
    step = "LOCK"
    committed = False
    start = time.monotonic()
    folder = None
    try:
        with lock(c["lock_file"]):
            folder = Path(c["local_backup_dir"]) / "runs" / rid
            folder.mkdir(parents=True)
            started = utc()
            log(c, "STARTED", run_id=rid)
            step = "DATABASE_BASELINE"
            baseline = snapshot(c, c["database"])
            step = "PG_DUMP"
            dump = folder / "database.dump"
            with dump.open("xb") as out:
                command(pg_args("pg_dump", "-w", "-Fc", "-d", c["database"]),
                        c["command_timeout_seconds"], stdout=out)
            with dump.open("rb") as inp:
                command(pg_args("pg_restore", "--list"), c["command_timeout_seconds"], stdin=inp)
            # This does not provide a cross-resource snapshot. Keep demo data quiescent.
            if snapshot(c, c["database"]) != baseline:
                raise LabError("Demo data changed during backup; retry with writers paused")
            step = "CONFIG_ARCHIVE"
            inventory = config_inventory(c["config_dir"])
            if sum(x["size"] for x in inventory) > c["max_backup_bytes"]:
                raise LabError("Configuration exceeds lab size limit")
            archive = folder / "configuration.tar.gz"
            with tarfile.open(archive, "w:gz", dereference=False) as tar:
                tar.add(c["config_dir"], arcname="config")
            if config_inventory(c["config_dir"]) != inventory:
                raise LabError("Config changed during backup; retry with writers paused")
            files = []
            for p in (dump, archive):
                size = p.stat().st_size
                if not 0 < size <= c["max_backup_bytes"]:
                    raise LabError("Invalid or oversized backup: " + p.name)
                files.append({"name": p.name, "size": size, "sha256": sha(p)})
            manifest = {"schema_version": 1, "run_id": rid, "started_at": started,
                        "database": c["database"], "db_version": query(c, c["database"], "SHOW server_version;"),
                        "files": files, "config_files": inventory, "demo_baseline": baseline}
            atomic_json(folder / "manifest.json", manifest)
            if (folder / "manifest.json").stat().st_size > 1024 * 1024:
                raise LabError("Manifest exceeds the lab restore limit of 1 MiB")
            step = "S3_UPLOAD"
            s3 = aws(c, "s3")
            prefix = f'{c["s3_prefix"]}/{rid}/'
            # Limit is 200 MiB by default; simple PUT avoids multipart permissions/cleanup.
            for name in ("database.dump", "configuration.tar.gz", "manifest.json"):
                p = folder / name
                with p.open("rb") as body:
                    s3.put_object(Bucket=c["s3_bucket"], Key=prefix + name, Body=body)
                head = s3.head_object(Bucket=c["s3_bucket"], Key=prefix + name)
                if head["ContentLength"] != p.stat().st_size:
                    raise LabError("S3 size mismatch: " + name)
            step = "COMMIT"
            success = {"schema_version": 1, "run_id": rid, "completed_at": utc(),
                       "manifest_sha256": sha(folder / "manifest.json")}
            atomic_json(folder / "SUCCESS.json", success)
            s3.put_object(Bucket=c["s3_bucket"], Key=prefix + "SUCCESS.json",
                          Body=(folder / "SUCCESS.json").read_bytes(), ContentType="application/json")
            committed = True
            step = "STATE"
            if c["update_state"]:
                atomic_json(Path(c["local_backup_dir"]) / "last_success.json", success)
            log(c, "BACKUP_SUCCESS", run_id=rid, seconds=round(time.monotonic() - start, 3),
                state_updated=c["update_state"])
            print("RUN_ID=" + rid)
            return 0
    except BusyError:
        log(c, "SKIPPED_LOCK", run_id=rid)
        return 75
    except Exception as exc:
        status = "MONITORING_FAILED" if committed else "BACKUP_FAILED"
        log(c, status, run_id=rid, step=step, error_type=type(exc).__name__, error=str(exc)[:1800])
        if folder:
            atomic_json(folder / "FAILED.json", {"run_id": rid, "utc": utc(), "step": step,
                                                 "s3_committed": committed, "error_type": type(exc).__name__})
        notify(c, rid, step, type(exc).__name__)
        return 2 if committed else 1


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", default="/etc/cloudbackup.json")
    args = p.parse_args()
    try:
        require_root()
        c = read_config(args.config)
        return execute(c)
    except Exception as exc:
        print("STARTUP_ERROR: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
