"""Shared lab utilities. Linux execution; no embedded AWS credentials."""
import contextlib
import datetime as dt
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import signal
import subprocess
import tarfile
import time
import uuid

RUN_RE = re.compile(r"^[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}$")
NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
DEMO_SQL = """
SELECT json_build_object(
 'columns',(SELECT json_agg(row_to_json(c)) FROM
   (SELECT column_name,data_type,is_nullable,column_default
    FROM information_schema.columns WHERE table_schema='public'
    AND table_name='demo_inventory' ORDER BY ordinal_position) c),
 'rows',(SELECT json_agg(row_to_json(r)) FROM
   (SELECT * FROM public.demo_inventory ORDER BY item_id) r),
 'constraints',(SELECT json_agg(row_to_json(k)) FROM
   (SELECT conname,pg_get_constraintdef(oid) AS definition
    FROM pg_constraint WHERE conrelid='public.demo_inventory'::regclass
    ORDER BY conname) k),
 'sequence',(SELECT row_to_json(s) FROM
   (SELECT last_value,is_called FROM public.demo_inventory_item_id_seq) s)
);
"""


class LabError(Exception):
    pass


class BusyError(LabError):
    pass


def utc():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def run_id():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:8]


def validate_run(value):
    if not RUN_RE.fullmatch(value):
        raise LabError("Invalid run_id")
    return value


def read_config(path):
    c = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    required = ["database", "config_dir", "local_backup_dir", "s3_bucket", "aws_region"]
    for key in required:
        if not c.get(key):
            raise LabError("Missing config: " + key)
    if not NAME_RE.fullmatch(c["database"]):
        raise LabError("Database name must be a simple lowercase identifier")
    if "THAY_" in c["s3_bucket"]:
        raise LabError("Replace the example bucket first")
    c.setdefault("s3_prefix", "backups")
    c["s3_prefix"] = c["s3_prefix"].strip("/")
    if not re.fullmatch(r"[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*", c["s3_prefix"]):
        raise LabError("Invalid s3_prefix")
    c.setdefault("sns_topic_arn", "")
    c.setdefault("project", "Nhom7")
    c.setdefault("environment", "demo")
    c.setdefault("namespace", "CloudBackup/Nhom7")
    c.setdefault("command_timeout_seconds", 120)
    c.setdefault("max_backup_bytes", 200 * 1024 * 1024)
    c.setdefault("overdue_seconds", 900)
    c.setdefault("update_state", True)
    c.setdefault("lock_file", "/var/lock/cloudbackup.lock")
    for key in ("config_dir", "local_backup_dir", "lock_file"):
        if not Path(c[key]).is_absolute():
            raise LabError(key + " must be an absolute path")
    for key in ("command_timeout_seconds", "max_backup_bytes", "overdue_seconds"):
        if not isinstance(c[key], int) or c[key] <= 0:
            raise LabError(key + " must be a positive integer")
    if not isinstance(c["update_state"], bool):
        raise LabError("update_state must be true or false")
    return c


def require_root():
    if not hasattr(os, "geteuid") or os.geteuid() != 0:
        raise LabError("Run on Linux using sudo and the project's venv Python")
    os.umask(0o077)


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp-" + uuid.uuid4().hex)
    try:
        with tmp.open("x", encoding="utf-8", newline="\n") as f:
            json.dump(value, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def log(c, event, **fields):
    root = Path(c["local_backup_dir"])
    root.mkdir(parents=True, exist_ok=True)
    record = {"utc": utc(), "event": event, **fields}
    line = json.dumps(record, ensure_ascii=False)
    with (root / "backup.log").open("a", encoding="utf-8") as f:
        f.write(line + "\n")
    print(line, flush=True)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for part in iter(lambda: f.read(1024 * 1024), b""):
            h.update(part)
    return h.hexdigest()


def aws(c, service):
    import boto3
    from botocore.config import Config
    return boto3.client(service, region_name=c["aws_region"], config=Config(
        connect_timeout=5, read_timeout=20,
        retries={"mode": "standard", "total_max_attempts": 3}))


@contextlib.contextmanager
def lock(path):
    import fcntl
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a") as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise BusyError("Another backup is already running") from exc
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def command(args, timeout, stdin=None, stdout=None):
    """Kill the whole Linux subprocess group on timeout, including pg_dump."""
    env = os.environ.copy()
    for k in list(env):
        if k.startswith("PG"):
            env.pop(k)
    env["LC_ALL"] = "C"
    p = subprocess.Popen(args, stdin=stdin, stdout=stdout or subprocess.PIPE,
                         stderr=subprocess.PIPE, cwd="/tmp", env=env,
                         start_new_session=True)
    try:
        out, err = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(p.pid, signal.SIGKILL)
        p.communicate()
        raise LabError("Command timeout: " + Path(args[0]).name)
    if p.returncode:
        # Lab input only. Do not pass passwords or secret config content to commands.
        raise LabError("Command failed: " + err.decode("utf-8", "replace")[-1500:])
    return out or b""


def pg_args(tool, *args):
    runuser = shutil.which("runuser")
    binary = shutil.which(tool)
    if not runuser or not binary:
        raise LabError("Missing runuser or PostgreSQL tool: " + tool)
    return [runuser, "-u", "postgres", "--", binary, *args]


def query(c, database, sql):
    return command(pg_args("psql", "-X", "-v", "ON_ERROR_STOP=1", "-A", "-t",
                           "-d", database, "-c", sql), c["command_timeout_seconds"]).decode().strip()


def snapshot(c, database):
    return json.loads(query(c, database, DEMO_SQL))


def config_inventory(root):
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise LabError("config_dir must be an existing real directory")
    result = []
    for p in sorted(root.rglob("*")):
        if p.is_symlink() or (not p.is_file() and not p.is_dir()):
            raise LabError("Config symlinks and special files are not allowed")
        if p.is_file():
            result.append({"path": p.relative_to(root).as_posix(),
                           "size": p.stat().st_size, "sha256": sha(p)})
    if not result:
        raise LabError("Config directory is empty")
    return result


def safe_extract(archive, dest, max_bytes):
    """Validate the whole archive before writing; never extract symlinks/devices."""
    dest = Path(dest)
    if dest.exists():
        raise LabError("Restore config destination must be new")
    with tarfile.open(archive, "r:gz") as tar:
        members = tar.getmembers()
        total = 0
        names = set()
        for m in members:
            p = PurePosixPath(m.name)
            if (p.is_absolute() or ".." in p.parts or "\\" in m.name or
                    not p.parts or p.parts[0] != "config" or
                    not (m.isdir() or m.isfile()) or p.as_posix() in names):
                raise LabError("Unsafe archive member: " + m.name)
            names.add(p.as_posix())
            total += m.size
            if total > max_bytes or len(names) > 10000:
                raise LabError("Archive exceeds lab extraction limit")
        dest.mkdir(parents=True)
        for m in members:
            target = dest.joinpath(*PurePosixPath(m.name).parts)
            if m.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                source = tar.extractfile(m)
                if source is None:
                    raise LabError("Cannot read archive member")
                with source, target.open("xb") as out:
                    shutil.copyfileobj(source, out)


def download(s3, bucket, key, target, limit):
    response = s3.get_object(Bucket=bucket, Key=key)
    body = response["Body"]
    total = 0
    try:
        if response.get("ContentLength", 0) > limit:
            raise LabError("S3 object exceeds size limit")
        with Path(target).open("xb") as out:
            while True:
                part = body.read(min(1024 * 1024, limit - total + 1))
                if not part:
                    break
                total += len(part)
                if total > limit:
                    raise LabError("S3 object exceeds size limit")
                out.write(part)
    finally:
        body.close()


def notify(c, rid, step, error_type):
    if not c["sns_topic_arn"]:
        log(c, "NOTIFICATION_NOT_CONFIGURED", run_id=rid)
        return
    try:
        result = aws(c, "sns").publish(
            TopicArn=c["sns_topic_arn"], Subject="CloudBackup Nhom7 FAILED",
            Message=f"Nhom7 backup FAILED\nUTC={utc()}\nrun={rid}\nstep={step}\ntype={error_type}\nCheck CloudWatch Logs.")
        log(c, "NOTIFICATION_PUBLISHED", run_id=rid, message_id=result["MessageId"])
    except Exception as exc:
        log(c, "NOTIFICATION_FAILED", run_id=rid, error_type=type(exc).__name__)


def backup_age(state, now, overdue):
    try:
        stamp = dt.datetime.fromisoformat(state["completed_at"])
        if stamp.tzinfo is None:
            raise ValueError("Missing timezone")
        age = now - stamp.timestamp()
        if age < -60:
            raise ValueError("Future timestamp")
        return max(0, age), "VALID"
    except (KeyError, ValueError, TypeError):
        return overdue + 1, "INVALID_OR_MISSING_STATE"
