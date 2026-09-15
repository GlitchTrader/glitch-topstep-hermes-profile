"""Fail-closed transactional updates for the installed Topstep profile.

The transaction keeps its manifest, package archive, rollback archive, and
receipts directly under the existing profile ``state`` directory.  It never
copies or removes user state, credentials, locks owned by another process, or
the NT ``glitch`` profile.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import uuid
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

PROFILE_NAME = "glitch-topstep"
CONTROL_FILES = {
    "profile-update-transaction.json",
    "profile-update-package.zip",
    "profile-update-rollback.zip",
    "profile-update-receipt.json",
    "profile-update.lock",
}
PROTECTED_NAMES = {".env", "auth.json", "config.yaml"}
PROTECTED_DIRS = {"state", "logs", "runtime", "cache", "sessions", "memories"}


class UpdateError(RuntimeError):
    """A safe update precondition or transaction invariant failed."""


def _norm_hash(data: bytes) -> str:
    return hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest().upper()


def _json_write_atomic(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_name(path.name + ".part")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _profile_root(root: Path) -> Path:
    root = root.resolve()
    if root.name.lower() != PROFILE_NAME:
        raise UpdateError(f"refusing non-Topstep profile root: {root}")
    if root.name.lower() == "glitch":
        raise UpdateError("refusing NT profile root")
    return root


def _state_root(root: Path) -> Path:
    state = root / "state"
    if not state.is_dir():
        raise UpdateError(f"existing state directory required: {state}")
    return state


def _read_owned_roots(root: Path) -> list[str]:
    yaml = root / "distribution.yaml"
    if not yaml.is_file():
        raise UpdateError("distribution.yaml missing")
    owned: list[str] = []
    active = False
    for line in yaml.read_text(encoding="utf-8").splitlines():
        if line.strip() == "distribution_owned:":
            active = True
            continue
        if active and line.startswith("  - "):
            owned.append(line[4:].strip().strip("\"'" ).replace("\\", "/"))
            continue
        if active and line and not line.startswith(" "):
            break
    if not owned:
        raise UpdateError("distribution_owned is empty")
    return owned


def _is_protected(relative: str) -> bool:
    parts = PurePosixPath(relative).parts
    return bool(parts) and (parts[0] in PROTECTED_DIRS or parts[0] in PROTECTED_NAMES or any(
        part in PROTECTED_NAMES or part.endswith((".db", ".db-wal", ".db-shm", ".lock"))
        for part in parts
    ))


def _owned_files(root: Path, *, require_roots: bool = False) -> list[str]:
    files: set[str] = set()
    for owned in _read_owned_roots(root):
        path = root / owned
        if require_roots and not path.exists():
            raise UpdateError(f"distributed root missing: {owned}")
        if path.is_file():
            candidates = [path]
        elif path.is_dir():
            candidates = [item for item in path.rglob("*") if item.is_file()]
        else:
            continue
        for item in candidates:
            relative = item.relative_to(root).as_posix()
            if relative not in CONTROL_FILES and not _is_protected(relative):
                files.add(relative)
    return sorted(files)


def _hash_manifest(root: Path, paths: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for relative in paths:
        path = root / Path(relative)
        if not path.is_file():
            raise UpdateError(f"distributed file missing: {relative}")
        result[relative] = _norm_hash(path.read_bytes())
    return result


def _read_contract(root: Path) -> dict[str, Any]:
    path = root / "paired-contract.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise UpdateError(f"invalid paired contract: {error}") from error
    if value.get("profile", {}).get("name") != PROFILE_NAME:
        raise UpdateError("paired contract is not for glitch-topstep")
    return value


def _read_sha_manifest(root: Path) -> dict[str, str]:
    manifest_path = root / "SHA256SUMS"
    try:
        lines = manifest_path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise UpdateError(f"SHA256SUMS is unreadable: {error}") from error
    entries: dict[str, str] = {}
    for line in lines:
        if not line.strip():
            continue
        parts = line.split(None, 1)
        if len(parts) != 2 or len(parts[0]) != 64:
            raise UpdateError("SHA256SUMS is invalid")
        entries[parts[1].strip()] = parts[0].upper()
    if not entries:
        raise UpdateError("SHA256SUMS is empty")
    return entries


def _validate_manifest(root: Path, hashes: dict[str, str]) -> None:
    for relative, expected_hash in _read_sha_manifest(root).items():
        if relative not in hashes:
            raise UpdateError(f"SHA256SUMS references missing distributed file: {relative}")
        if hashes[relative] != expected_hash:
            raise UpdateError(f"distributed file drift detected: {relative}")


def _validate_package(package: Path, expected_prompt: str | None = None) -> tuple[list[str], dict[str, str], dict[str, Any]]:
    package = package.resolve()
    if not package.is_dir() or package.name.lower() == "glitch":
        raise UpdateError(f"invalid package root: {package}")
    if (package / ".git").exists():
        raise UpdateError("refusing a VCS checkout as an install package")
    contract = _read_contract(package)
    prompt = contract.get("profile", {}).get("prompt_version")
    if expected_prompt and prompt != expected_prompt:
        raise UpdateError(f"prompt_version incompatible: {prompt!r}")
    paths = _owned_files(package, require_roots=True)
    hashes = _hash_manifest(package, paths)
    if not paths or "SHA256SUMS" not in hashes:
        raise UpdateError("package has no complete distributed manifest")
    for relative, expected_hash in _read_sha_manifest(package).items():
        if relative not in hashes:
            raise UpdateError(f"package SHA256SUMS references missing file: {relative}")
        if hashes[relative] != expected_hash:
            raise UpdateError(f"package SHA256SUMS mismatch: {relative}")
    return paths, hashes, contract


def validate_process_inventory(processes: list[dict[str, Any]]) -> None:
    """Reject ambiguous or concurrent owners without inspecting credentials."""
    for process in processes:
        profile = str(process.get("profile", ""))
        if profile == "glitch":
            continue  # NT is protected and never an update target.
        if profile == PROFILE_NAME:
            raise UpdateError("Topstep profile process is already running")
        if process.get("hermes_gateway"):
            raise UpdateError("Hermes gateway owner is unverified")


def _zip_files(archive: Path, root: Path, paths: list[str]) -> None:
    temporary = archive.with_name(archive.name + ".part")
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as output:
        for relative in paths:
            output.write(root / Path(relative), relative)
    os.replace(temporary, archive)


def _extract_archive(archive: Path, root: Path, expected: dict[str, str]) -> None:
    with zipfile.ZipFile(archive) as source:
        names = set(source.namelist())
        if set(expected) - names:
            raise UpdateError("rollback archive is incomplete")
        for relative, expected_hash in expected.items():
            if _is_protected(relative):
                raise UpdateError(f"rollback archive contains protected path: {relative}")
            target = root / Path(relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name(target.name + ".update-part")
            temporary.write_bytes(source.read(relative))
            if _norm_hash(temporary.read_bytes()) != expected_hash:
                temporary.unlink(missing_ok=True)
                raise UpdateError(f"rollback hash mismatch: {relative}")
            os.replace(temporary, target)


def _remove_distributed_paths(root: Path, paths: set[str]) -> None:
    for relative in sorted(paths):
        if _is_protected(relative):
            raise UpdateError(f"refusing to remove protected path: {relative}")
        target = root / Path(relative)
        if target.is_file():
            target.unlink()


def _acquire_lock(state: Path, transaction_id: str) -> Path:
    path = state / "profile-update.lock"
    try:
        with path.open("x", encoding="utf-8") as handle:
            json.dump({"transaction_id": transaction_id, "pid": os.getpid()}, handle)
    except FileExistsError as error:
        raise UpdateError("profile update lock exists; owner is not verified") from error
    return path


def _receipt(state: Path, payload: dict[str, Any]) -> None:
    _json_write_atomic(state / "profile-update-receipt.json", payload)


def verify_installation(root: Path) -> dict[str, Any]:
    root = _profile_root(root)
    paths = _owned_files(root)
    hashes = _hash_manifest(root, paths)
    _validate_manifest(root, hashes)
    contract = _read_contract(root)
    return {
        "state": "verified",
        "profile": PROFILE_NAME,
        "root": str(root),
        "version": contract.get("profile", {}).get("version"),
        "prompt_version": contract.get("profile", {}).get("prompt_version"),
        "files": len(paths),
        "hashes": hashes,
    }


def recover_incomplete(root: Path) -> dict[str, Any]:
    root = _profile_root(root)
    state = _state_root(root)
    transaction_path = state / "profile-update-transaction.json"
    if not transaction_path.is_file():
        return {"state": "clean"}
    transaction = json.loads(transaction_path.read_text(encoding="utf-8"))
    phase = transaction.get("phase")
    if phase in {"prepared", "validated"}:
        result = {"state": "aborted", "transaction_id": transaction.get("transaction_id")}
    elif phase == "applying":
        old_hashes = transaction.get("old_hashes", {})
        _extract_archive(state / "profile-update-rollback.zip", root, old_hashes)
        _remove_distributed_paths(root, set(transaction.get("new_hashes", {})) - set(old_hashes))
        result = {"state": "rolled_back_after_interruption", "transaction_id": transaction.get("transaction_id")}
    else:
        return {"state": "no_recovery_needed", "phase": phase}
    _receipt(state, {**result, "operation": "recovery"})
    transaction_path.unlink(missing_ok=True)
    return result


def transactional_update(root: Path, package: Path, expected_prompt: str | None = None) -> dict[str, Any]:
    root = _profile_root(root)
    package = package.resolve()
    state = _state_root(root)
    recover_incomplete(root)
    transaction_id = uuid.uuid4().hex
    lock = _acquire_lock(state, transaction_id)
    try:
        package_paths, package_hashes, package_contract = _validate_package(package, expected_prompt)
        old_paths = _owned_files(root)
        old_hashes = _hash_manifest(root, old_paths)
        _validate_manifest(root, old_hashes)
        rollback = state / "profile-update-rollback.zip"
        _zip_files(rollback, root, old_paths)
        package_archive = state / "profile-update-package.zip"
        _zip_files(package_archive, package, package_paths)
        transaction = {
            "schema_version": "glitch.topstep.profile_update_transaction.v1",
            "transaction_id": transaction_id,
            "profile": PROFILE_NAME,
            "phase": "validated",
            "old_hashes": old_hashes,
            "new_hashes": package_hashes,
            "new_profile_version": package_contract["profile"].get("version"),
            "new_prompt_version": package_contract["profile"].get("prompt_version"),
            "rollback_archive": rollback.name,
            "package_archive": package_archive.name,
            "protected": sorted(PROTECTED_NAMES | PROTECTED_DIRS),
        }
        _json_write_atomic(state / "profile-update-transaction.json", transaction)
        transaction["phase"] = "applying"
        _json_write_atomic(state / "profile-update-transaction.json", transaction)
        _remove_distributed_paths(root, set(old_hashes) - set(package_hashes))
        with zipfile.ZipFile(package_archive) as source:
            for relative in package_paths:
                target = root / Path(relative)
                target.parent.mkdir(parents=True, exist_ok=True)
                temporary = target.with_name(target.name + ".update-part")
                temporary.write_bytes(source.read(relative))
                if _norm_hash(temporary.read_bytes()) != package_hashes[relative]:
                    raise UpdateError(f"package hash changed during update: {relative}")
                os.replace(temporary, target)
        if _hash_manifest(root, package_paths) != package_hashes:
            raise UpdateError("post-update hash verification failed")
        transaction["phase"] = "committed"
        _json_write_atomic(state / "profile-update-transaction.json", transaction)
        _receipt(state, {"state": "committed", "operation": "update", "transaction_id": transaction_id,
                         "old_hashes": old_hashes, "new_hashes": package_hashes})
        return {"state": "committed", "transaction_id": transaction_id}
    except Exception as error:
        try:
            transaction_path = state / "profile-update-transaction.json"
            if transaction_path.is_file():
                transaction = json.loads(transaction_path.read_text(encoding="utf-8"))
                if transaction.get("phase") == "applying":
                    _extract_archive(state / "profile-update-rollback.zip", root, transaction.get("old_hashes", {}))
                    _remove_distributed_paths(root, set(transaction.get("new_hashes", {})) - set(transaction.get("old_hashes", {})))
            _receipt(state, {"state": "rolled_back", "operation": "update", "transaction_id": transaction_id,
                             "error": str(error)})
        except Exception as rollback_error:
            raise UpdateError(f"update failed and rollback failed: {rollback_error}") from error
        raise
    finally:
        (state / "profile-update-transaction.json").unlink(missing_ok=True)
        lock.unlink(missing_ok=True)


def rollback(root: Path) -> dict[str, Any]:
    root = _profile_root(root)
    state = _state_root(root)
    transaction_id = uuid.uuid4().hex
    lock = _acquire_lock(state, transaction_id)
    try:
        receipt = state / "profile-update-receipt.json"
        if not receipt.is_file():
            raise UpdateError("no update receipt available for rollback")
        data = json.loads(receipt.read_text(encoding="utf-8"))
        old_hashes = data.get("old_hashes")
        if not isinstance(old_hashes, dict) or not old_hashes:
            raise UpdateError("rollback receipt has no previous distributed hashes")
        _extract_archive(state / "profile-update-rollback.zip", root, old_hashes)
        _remove_distributed_paths(root, set(data.get("new_hashes", {})) - set(old_hashes))
        _receipt(state, {"state": "rolled_back", "operation": "rollback", "transaction_id": transaction_id,
                         "old_hashes": old_hashes, "new_hashes": data.get("new_hashes", {}),
                         "restored_hashes": old_hashes})
        return {"state": "rolled_back", "transaction_id": transaction_id}
    finally:
        lock.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("verify", "recover", "update", "rollback"))
    parser.add_argument("root", type=Path)
    parser.add_argument("--package-root", type=Path)
    parser.add_argument("--expected-prompt")
    args = parser.parse_args(argv)
    try:
        if args.operation == "verify":
            result = verify_installation(args.root)
        elif args.operation == "recover":
            result = recover_incomplete(args.root)
        elif args.operation == "rollback":
            result = rollback(args.root)
        else:
            if args.package_root is None:
                raise UpdateError("update requires --package-root for pre-validation")
            result = transactional_update(args.root, args.package_root, args.expected_prompt)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (OSError, UpdateError, ValueError, zipfile.BadZipFile) as error:
        print(json.dumps({"state": "error", "error": str(error)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
