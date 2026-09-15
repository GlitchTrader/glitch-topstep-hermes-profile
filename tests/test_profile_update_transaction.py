from __future__ import annotations

import json
import hashlib
import os
import shutil
import tempfile
import unittest
import getpass
from pathlib import Path
from unittest import mock

from scripts.profile_update_transaction import (
    UpdateError,
    _acquire_lock,
    recover_incomplete,
    rollback,
    transactional_update,
    verify_installation,
)


def make_profile(root: Path, version: str, prompt: str = "glitch-topstep-v17.2") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "state").mkdir()
    (root / "skills").mkdir()
    (root / "distribution.yaml").write_text(
        "name: glitch-topstep\nversion: %s\ndistribution_owned:\n  - distribution.yaml\n  - paired-contract.json\n  - SHA256SUMS\n  - skills\n"
        % version,
        encoding="utf-8",
    )
    (root / "paired-contract.json").write_text(json.dumps({
        "profile": {"name": "glitch-topstep", "version": version, "prompt_version": prompt}
    }) + "\n", encoding="utf-8")
    (root / "skills" / "example.md").write_text("---\nname: example\n---\n", encoding="utf-8")
    manifest_paths = [root / "distribution.yaml", root / "paired-contract.json", root / "skills" / "example.md"]
    manifest = []
    for path in manifest_paths:
        digest = hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest().upper()
        manifest.append(f"{digest}  {path.relative_to(root).as_posix()}")
    (root / "SHA256SUMS").write_text("\n".join(manifest) + "\n", encoding="utf-8")
    (root / ".env").write_text("SECRET=must-stay\n", encoding="utf-8")
    (root / "auth.json").write_text("{\"credential\":\"must-stay\"}\n", encoding="utf-8")
    (root / "state.db").write_bytes(b"db")
    (root / "state.db-wal").write_bytes(b"wal")
    (root / "state.db-shm").write_bytes(b"shm")
    return root


class ProfileUpdateTransactionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        self.target = make_profile(base / "glitch-topstep", "0.2.9")
        self.package = make_profile(base / "package", "0.2.10")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_update_records_hashes_and_preserves_user_state(self) -> None:
        result = transactional_update(self.target, self.package)
        self.assertEqual(result["state"], "committed")
        self.assertEqual((self.target / ".env").read_text(), "SECRET=must-stay\n")
        self.assertEqual((self.target / "auth.json").read_text(), "{\"credential\":\"must-stay\"}\n")
        self.assertEqual((self.target / "state.db").read_bytes(), b"db")
        self.assertEqual((self.target / "state.db-wal").read_bytes(), b"wal")
        self.assertEqual((self.target / "state.db-shm").read_bytes(), b"shm")
        receipt = json.loads((self.target / "state" / "profile-update-receipt.json").read_text())
        self.assertTrue(receipt["old_hashes"])
        self.assertEqual((self.target / "paired-contract.json").read_text(), (self.package / "paired-contract.json").read_text())

    def test_rollback_restores_previous_distribution(self) -> None:
        before = (self.target / "skills" / "example.md").read_bytes()
        transactional_update(self.target, self.package)
        (self.target / "skills" / "example.md").write_text("changed", encoding="utf-8")
        self.assertEqual(rollback(self.target)["state"], "rolled_back")
        self.assertEqual((self.target / "skills" / "example.md").read_bytes(), before)
        self.assertEqual(rollback(self.target)["state"], "rolled_back")

    def test_incompatible_package_is_rejected_before_swap(self) -> None:
        before = (self.target / "paired-contract.json").read_bytes()
        with self.assertRaises(UpdateError):
            transactional_update(self.target, self.package, expected_prompt="glitch-topstep-v99")
        self.assertEqual((self.target / "paired-contract.json").read_bytes(), before)

    def test_hash_drift_and_missing_distributed_root_are_rejected(self) -> None:
        (self.package / "SHA256SUMS").write_text("0" * 64 + "  distribution.yaml\n", encoding="utf-8")
        with self.assertRaises(UpdateError):
            transactional_update(self.target, self.package)
        package_without_skills = Path(self.temp.name) / "missing-skills"
        shutil.copytree(self.package, package_without_skills)
        shutil.rmtree(package_without_skills / "skills")
        with self.assertRaises(UpdateError):
            transactional_update(self.target, package_without_skills)

    def test_existing_distributed_drift_is_rejected_before_swap(self) -> None:
        before = (self.target / "paired-contract.json").read_bytes()
        (self.target / "skills" / "example.md").write_text("unexplained drift", encoding="utf-8")
        with self.assertRaisesRegex(UpdateError, "drift detected"):
            transactional_update(self.target, self.package)
        self.assertEqual((self.target / "paired-contract.json").read_bytes(), before)

    def test_failure_during_swap_rolls_back(self) -> None:
        before = (self.target / "skills" / "example.md").read_bytes()
        real_replace = os.replace
        calls = {"count": 0}

        def fail_once(source: str | os.PathLike[str], destination: str | os.PathLike[str]) -> None:
            calls["count"] += 1
            if calls["count"] == 3:
                raise OSError("simulated interruption")
            real_replace(source, destination)

        with mock.patch("scripts.profile_update_transaction.os.replace", side_effect=fail_once):
            with self.assertRaises(OSError):
                transactional_update(self.target, self.package)
        self.assertEqual((self.target / "skills" / "example.md").read_bytes(), before)

    def test_recovery_rolls_back_incomplete_transaction(self) -> None:
        transactional_update(self.target, self.package)
        receipt = json.loads((self.target / "state" / "profile-update-receipt.json").read_text())
        previous = (self.target / "skills" / "example.md").read_bytes()
        tx = {
            "transaction_id": "interrupted",
            "phase": "applying",
            "old_hashes": receipt["old_hashes"],
            "new_hashes": receipt["new_hashes"],
        }
        (self.target / "state" / "profile-update-transaction.json").write_text(json.dumps(tx), encoding="utf-8")
        self.assertEqual(recover_incomplete(self.target)["state"], "rolled_back_after_interruption")

    def test_other_owner_lock_and_nt_root_are_rejected(self) -> None:
        lock = self.target / "state" / "profile-update.lock"
        lock.write_text(json.dumps({"pid": 9999, "owner": "other"}), encoding="utf-8")
        with self.assertRaises(UpdateError):
            transactional_update(self.target, self.package)
        with self.assertRaises(UpdateError):
            verify_installation(self.target.with_name("glitch"))

    def test_orphan_lock_is_recovered_and_followup_update_works(self) -> None:
        lock = self.target / "state" / "profile-update.lock"
        lock.write_text(json.dumps({
            "pid": 999999,
            "process_start_identity": "1.0",
            "transaction_id": "orphaned",
            "owner": getpass.getuser(),
        }), encoding="utf-8")
        result = recover_incomplete(self.target)
        self.assertEqual(result["state"], "orphan_lock_recovered")
        self.assertFalse(lock.exists())
        self.assertEqual(transactional_update(self.target, self.package)["state"], "committed")
        self.assertEqual(rollback(self.target)["state"], "rolled_back")

    def test_real_acquire_lock_crash_recover_rollback_and_new_operation(self) -> None:
        from scripts import profile_update_transaction as updater

        transactional_update(self.target, self.package)
        receipt = json.loads((self.target / "state" / "profile-update-receipt.json").read_text())
        previous = (self.target / "skills" / "example.md").read_bytes()
        lock = _acquire_lock(self.target / "state", "crashed-transaction")
        lock_record = json.loads(lock.read_text(encoding="utf-8"))
        self.assertEqual(lock_record["transaction_id"], "crashed-transaction")
        self.assertIn("pid", lock_record)
        self.assertIn("process_start_identity", lock_record)
        self.assertIn("owner", lock_record)
        (self.target / "skills" / "example.md").write_text("partially applied", encoding="utf-8")
        (self.target / "state" / "profile-update-transaction.json").write_text(
            json.dumps({
                "transaction_id": "crashed-transaction",
                "phase": "applying",
                "old_hashes": receipt["old_hashes"],
                "new_hashes": receipt["new_hashes"],
            }), encoding="utf-8",
        )
        with mock.patch.object(updater, "_process_state", return_value="dead"):
            result = recover_incomplete(self.target)
        self.assertEqual(result["state"], "rolled_back_after_interruption")
        self.assertEqual((self.target / "skills" / "example.md").read_bytes(), previous)
        recovery_receipt = json.loads((self.target / "state" / "profile-update-receipt.json").read_text())
        self.assertEqual(recovery_receipt["lock_recovery"]["state"], "orphan_lock_recovered")
        self.assertFalse(lock.exists())
        self.assertEqual(transactional_update(self.target, self.package)["state"], "committed")

    def test_live_reused_and_unknown_lock_are_fail_closed(self) -> None:
        lock = self.target / "state" / "profile-update.lock"
        current = os.getpid()
        lock.write_text(json.dumps({
            "pid": current,
            "process_start_identity": "wrong",
            "transaction_id": "reused",
            "owner": getpass.getuser(),
        }), encoding="utf-8")
        self.assertEqual(recover_incomplete(self.target)["process_state"], "reused")
        from scripts.profile_update_transaction import _process_start_identity
        lock.write_text(json.dumps({
            "pid": current,
            "process_start_identity": _process_start_identity(current),
            "transaction_id": "live-owner",
            "owner": getpass.getuser(),
        }), encoding="utf-8")
        with self.assertRaisesRegex(UpdateError, "owner is alive"):
            recover_incomplete(self.target)
        lock.unlink()
        lock.write_text(json.dumps({
            "pid": 999999,
            "process_start_identity": "1.0",
            "transaction_id": "unknown-owner",
            "owner": "unknown-owner",
        }), encoding="utf-8")
        with self.assertRaisesRegex(UpdateError, "another owner"):
            recover_incomplete(self.target)

    def test_inventory_is_checked_by_update_rollback_recover_and_main(self) -> None:
        from scripts import profile_update_transaction as updater

        active = [{"profile": "glitch-topstep", "pid": 7}]
        with mock.patch.object(updater, "collect_process_inventory", return_value=active):
            with self.assertRaisesRegex(UpdateError, "already running"):
                transactional_update(self.target, self.package)
            with self.assertRaisesRegex(UpdateError, "already running"):
                rollback(self.target)
            with self.assertRaisesRegex(UpdateError, "already running"):
                recover_incomplete(self.target)
            self.assertNotEqual(updater.main(["verify", str(self.target)]), 0)
        with mock.patch.object(updater, "collect_process_inventory", return_value=[{"profile": "glitch", "pid": 20716}]):
            self.assertEqual(updater.main(["verify", str(self.target)]), 0)

    def test_unsafe_package_path_and_case_insensitive_protection_are_rejected(self) -> None:
        from scripts.profile_update_transaction import _is_protected

        self.assertTrue(_is_protected("AUTH.JSON"))
        self.assertTrue(_is_protected("State.DB-WAL"))
        (self.package / "distribution.yaml").write_text(
            "name: glitch-topstep\nversion: 0.2.10\ndistribution_owned:\n  - ../glitch\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(UpdateError, "unsafe distributed path"):
            transactional_update(self.target, self.package)

    def test_process_inventory_protects_nt_and_rejects_topstep_owner(self) -> None:
        from scripts.profile_update_transaction import validate_process_inventory

        validate_process_inventory([{"profile": "glitch", "pid": 20716}])
        with self.assertRaises(UpdateError):
            validate_process_inventory([{"profile": "glitch-topstep", "pid": 9}])
        with self.assertRaises(UpdateError):
            validate_process_inventory([{"profile": "other", "hermes_gateway": True}])

    def test_utf8_path_with_spaces_and_no_new_control_directory(self) -> None:
        base = Path(self.temp.name) / "profile update fixture"
        target = make_profile(base / "glitch-topstep", "0.2.9")
        package = make_profile(base / "package", "0.2.10")
        (package / "skills" / "example.md").write_text("---\nname: café\n---\n", encoding="utf-8")
        manifest_paths = ("distribution.yaml", "paired-contract.json", "skills/example.md")
        manifest = []
        for relative in manifest_paths:
            digest = hashlib.sha256(
                (package / relative).read_bytes().replace(b"\r\n", b"\n")
            ).hexdigest().upper()
            manifest.append(f"{digest}  {relative}")
        (package / "SHA256SUMS").write_text("\n".join(manifest) + "\n", encoding="utf-8")
        self.assertEqual(transactional_update(target, package)["state"], "committed")
        self.assertIn("café", (target / "skills" / "example.md").read_text(encoding="utf-8"))
        self.assertTrue(all(item.is_file() for item in (target / "state").iterdir()))

    def test_verify_is_idempotent_and_protected_files_are_not_manifested(self) -> None:
        first = verify_installation(self.target)
        second = verify_installation(self.target)
        self.assertEqual(first, second)
        self.assertNotIn(".env", first["hashes"])
        self.assertNotIn("state.db", first["hashes"])


if __name__ == "__main__":
    unittest.main()
