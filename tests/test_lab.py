"""Offline behavior checks. AWS and PostgreSQL are simulated, not integration-tested."""
import contextlib
import datetime as dt
import io
import json
import os
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import common
import backup
import restore_test
import heartbeat
import list_backups


class FakeS3:
    def __init__(self):
        self.objects = {}
        self.writes = []
        self.fail_key = None

    def put_object(self, Bucket, Key, Body, **kwargs):
        if self.fail_key and Key.endswith(self.fail_key):
            raise RuntimeError("simulated upload denied")
        self.objects[Key] = Body.read() if hasattr(Body, "read") else Body
        self.writes.append(Key)

    def head_object(self, Bucket, Key):
        return {"ContentLength": len(self.objects[Key])}

    def get_object(self, Bucket, Key):
        value = self.objects[Key]
        return {"Body": io.BytesIO(value), "ContentLength": len(value)}

    def get_paginator(self, name):
        return self

    def paginate(self, Bucket, Prefix):
        # One object/page forces callers to paginate.
        for key, body in self.objects.items():
            if key.startswith(Prefix):
                yield {"Contents": [{"Key": key, "Size": len(body)}]}


class FlowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        (root / "config" / "sub").mkdir(parents=True)
        (root / "config" / "app.conf").write_text("version=1\n")
        (root / "config" / "sub" / "worker.conf").write_text("enabled=true\n")
        self.c = {"database": "cloud_backup_demo", "config_dir": str(root / "config"),
                  "local_backup_dir": str(root / "local"), "s3_bucket": "test-bucket", "s3_prefix": "backups",
                  "aws_region": "ap-southeast-1", "sns_topic_arn": "", "lock_file": str(root / "lock"),
                  "command_timeout_seconds": 10, "max_backup_bytes": 1024 * 1024, "update_state": True,
                  "overdue_seconds": 900, "namespace": "CloudBackup/Nhom7", "project": "Nhom7", "environment": "demo"}
        self.s3 = FakeS3()
        self.baseline = {"rows": [{"item_id": 1, "quantity": 3}], "columns": ["id"], "sequence": {"last_value": 1}}
        self.patches = [
            patch.object(backup, "aws", return_value=self.s3),
            patch.object(backup, "lock", side_effect=lambda x: contextlib.nullcontext()),
            patch.object(backup, "snapshot", return_value=self.baseline),
            patch.object(backup, "pg_args", side_effect=lambda *x: list(x)),
            patch.object(backup, "query", return_value="15"),
            patch.object(backup, "command", side_effect=self.fake_command),
            patch.object(restore_test, "aws", return_value=self.s3),
            patch.object(restore_test, "pg_args", side_effect=lambda *x: list(x)),
            patch.object(restore_test, "snapshot", return_value=self.baseline),
            patch.object(restore_test, "command", side_effect=self.fake_command),
        ]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)

    def fake_command(self, args, timeout, stdin=None, stdout=None):
        if stdout is not None:
            stdout.write(b"fake PostgreSQL custom dump")
        return b""

    def successful_backup(self):
        self.assertEqual(backup.execute(self.c), 0)
        state = json.loads((Path(self.c["local_backup_dir"]) / "last_success.json").read_text())
        return state["run_id"]

    def test_success_marker_last_and_restore(self):
        rid = self.successful_backup()
        self.assertTrue(self.s3.writes[-1].endswith("SUCCESS.json"))
        self.assertEqual(restore_test.execute(self.c, rid), 0)
        results = list((Path(self.c["local_backup_dir"]) / "restore").glob("*/result.json"))
        result = json.loads(results[0].read_text())
        self.assertEqual(result["status"], "RESTORE_PASS")
        self.assertNotEqual(result["database"], self.c["database"])

    def test_upload_failure_no_commit_no_state(self):
        self.s3.fail_key = "configuration.tar.gz"
        with patch.object(backup, "notify") as notify:
            self.assertEqual(backup.execute(self.c), 1)
            notify.assert_called_once()
        self.assertFalse(any(k.endswith("SUCCESS.json") for k in self.s3.objects))
        self.assertFalse((Path(self.c["local_backup_dir"]) / "last_success.json").exists())

    def test_failed_run_keeps_previous_state(self):
        self.successful_backup()
        state = Path(self.c["local_backup_dir"]) / "last_success.json"
        before = state.read_bytes()
        self.s3.fail_key = "database.dump"
        with patch.object(backup, "notify"):
            self.assertEqual(backup.execute(self.c), 1)
        self.assertEqual(state.read_bytes(), before)

    def test_checksum_damage_stops_before_database(self):
        rid = self.successful_backup()
        key = f"backups/{rid}/database.dump"
        self.s3.objects[key] = b"X" + self.s3.objects[key][1:]
        with patch.object(restore_test, "command") as command:
            self.assertEqual(restore_test.execute(self.c, rid), 1)
            command.assert_not_called()

    def test_missing_marker_stops_before_database(self):
        rid = self.successful_backup()
        del self.s3.objects[f"backups/{rid}/SUCCESS.json"]
        with patch.object(restore_test, "command") as command:
            self.assertEqual(restore_test.execute(self.c, rid), 1)
            command.assert_not_called()

    def test_modified_manifest_rejected(self):
        rid = self.successful_backup()
        self.s3.objects[f"backups/{rid}/manifest.json"] += b" "
        self.assertEqual(restore_test.execute(self.c, rid), 1)

    def test_old_version_restores_its_original_config(self):
        rid = self.successful_backup()
        (Path(self.c["config_dir"]) / "app.conf").write_text("version=2\n")
        self.successful_backup()
        self.assertEqual(restore_test.execute(self.c, rid), 0)
        recovered = list((Path(self.c["local_backup_dir"]) / "restore").glob("*/recovered/config/app.conf"))
        self.assertEqual(recovered[0].read_text(), "version=1\n")

    def test_busy_run_does_not_upload(self):
        with patch.object(backup, "lock", side_effect=common.BusyError("busy")):
            self.assertEqual(backup.execute(self.c), 75)
        self.assertFalse(self.s3.writes)

    def test_test_config_cannot_refresh_good_state(self):
        self.c["update_state"] = False
        self.assertEqual(backup.execute(self.c), 0)
        self.assertFalse((Path(self.c["local_backup_dir"]) / "last_success.json").exists())

    def test_list_pagination_and_ignore_week1(self):
        rid = self.successful_backup()
        self.s3.objects["backups/test-backup.txt"] = b"week1"
        output = io.StringIO()
        with patch.object(list_backups, "aws", return_value=self.s3), contextlib.redirect_stdout(output):
            list_backups.execute(self.c)
        self.assertIn(rid, output.getvalue())
        self.assertIn("SUCCESS_MARKER", output.getvalue())
        self.assertNotIn("week1", output.getvalue())

    def test_verify_only_does_not_call_postgres(self):
        rid = self.successful_backup()
        with patch.object(restore_test, "command") as command:
            self.assertEqual(restore_test.execute(self.c, rid, verify_only=True), 0)
            command.assert_not_called()

    def test_state_write_failure_keeps_committed_backup(self):
        real_atomic = common.atomic_json
        def fail_state(path, value):
            if Path(path).name == "last_success.json":
                raise OSError("simulated state failure")
            return real_atomic(path, value)
        with patch.object(backup, "atomic_json", side_effect=fail_state), patch.object(backup, "notify"):
            self.assertEqual(backup.execute(self.c), 2)
        self.assertTrue(any(k.endswith("SUCCESS.json") for k in self.s3.objects))


class SafetyTests(unittest.TestCase):
    def test_archive_traversal_and_link_rejected(self):
        for name, kind in [("config/../../escape", tarfile.REGTYPE), ("config/link", tarfile.SYMTYPE)]:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                archive = Path(tmp) / "test.tar.gz"
                with tarfile.open(archive, "w:gz") as tar:
                    info = tarfile.TarInfo(name)
                    info.type = kind
                    info.linkname = "/etc/passwd" if kind == tarfile.SYMTYPE else ""
                    tar.addfile(info)
                with self.assertRaises(common.LabError):
                    common.safe_extract(archive, Path(tmp) / "out", 100)
                self.assertFalse((Path(tmp) / "out").exists())

    def test_download_cap(self):
        fake = FakeS3()
        fake.objects["x"] = b"too long"
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(common.LabError):
            common.download(fake, "bucket", "x", Path(tmp) / "x", 3)

    def test_invalid_run_id(self):
        for rid in ("../evil", "", "20261106T000000Z-12345678/x"):
            with self.assertRaises(common.LabError):
                common.validate_run(rid)

    def test_age_missing_old_future(self):
        now = dt.datetime(2026, 11, 6, tzinfo=dt.timezone.utc).timestamp()
        self.assertGreater(common.backup_age({}, now, 900)[0], 900)
        self.assertEqual(common.backup_age({"completed_at": "2026-11-05T23:40:00+00:00"}, now, 900)[0], 1200)
        self.assertEqual(common.backup_age({"completed_at": "2026-11-07T00:00:00+00:00"}, now, 900)[1], "INVALID_OR_MISSING_STATE")

    @unittest.skipUnless(os.name == "posix", "Requires Linux flock")
    def test_real_lock_contention(self):
        with tempfile.TemporaryDirectory() as tmp:
            with common.lock(Path(tmp) / "lock"):
                with self.assertRaises(common.BusyError):
                    with common.lock(Path(tmp) / "lock"):
                        pass

    @unittest.skipUnless(os.name == "posix", "Requires Linux process groups")
    def test_real_timeout(self):
        with self.assertRaisesRegex(common.LabError, "timeout"):
            common.command([sys.executable, "-c", "import time; time.sleep(20)"], .1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
