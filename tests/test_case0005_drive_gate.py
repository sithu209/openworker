from __future__ import annotations

import copy

import pytest

from scripts.case0005_drive_gate import SCHEMA, _validate_receipt


FOLDER = "drive-folder-123"
MANIFEST = "a" * 64
REVISION = "rev_1234567890abcdef"
FILES = [
    {"relative_path": "final/final.mp4", "sha256": "b" * 64, "drive_file_id": "file-video"},
    {"relative_path": "final/review-contact-sheet.jpg", "sha256": "c" * 64, "drive_file_id": "file-sheet"},
    {"relative_path": ".openworker/revisions/rev_1234567890abcdef/manifest.json", "sha256": "d" * 64, "drive_file_id": "file-manifest"},
]


def receipt(step_id: str = "0005-100") -> dict:
    value = {
        "schema_version": SCHEMA,
        "case_id": "0005",
        "step_id": step_id,
        "drive_revision_folder_id": FOLDER,
        "bundle_manifest_sha256": MANIFEST,
        "decision": "PASS" if step_id == "0005-100" else "APPROVE",
        "reviewer": "chatgpt",
        "reviewed_files": copy.deepcopy(FILES if step_id == "0005-100" else FILES[:1]),
    }
    if step_id == "0005-100":
        value["workledger_revision_id"] = REVISION
    return value


def validate(value: dict, *, step_id: str = "0005-100", expected_files=None) -> tuple[str, str]:
    return _validate_receipt(
        value,
        step_id=step_id,
        folder_id=FOLDER,
        manifest_sha=MANIFEST,
        expected_files=expected_files or (FILES if step_id == "0005-100" else FILES[:1]),
        expected_workledger_revision_id=REVISION if step_id == "0005-100" else "",
    )


def test_final_receipt_accepts_exact_bound_file_set() -> None:
    assert validate(receipt()) == ("PASS", "chatgpt")


def test_storyboard_receipt_accepts_only_approval_semantics() -> None:
    value = receipt("0005-027")
    assert validate(value, step_id="0005-027") == ("APPROVE", "chatgpt")


def test_wrong_parent_folder_is_rejected() -> None:
    value = receipt()
    value["drive_revision_folder_id"] = "other-folder"
    with pytest.raises(RuntimeError, match="folder identity mismatch"):
        validate(value)


def test_wrong_bundle_manifest_sha_is_rejected() -> None:
    value = receipt()
    value["bundle_manifest_sha256"] = "e" * 64
    with pytest.raises(RuntimeError, match="manifest SHA mismatch"):
        validate(value)


@pytest.mark.parametrize("field", ["command", "commands", "tool"])
def test_command_ingress_fields_are_rejected(field: str) -> None:
    value = receipt()
    value[field] = "do-something"
    with pytest.raises(RuntimeError, match="must not contain command/tool fields"):
        validate(value)


def test_wrong_drive_file_id_is_rejected() -> None:
    value = receipt()
    value["reviewed_files"][0]["drive_file_id"] = "wrong-file"
    with pytest.raises(RuntimeError, match="reviewed file identities"):
        validate(value)


def test_wrong_artifact_sha_is_rejected() -> None:
    value = receipt()
    value["reviewed_files"][1]["sha256"] = "f" * 64
    with pytest.raises(RuntimeError, match="reviewed file identities"):
        validate(value)


def test_missing_or_extra_reviewed_file_is_rejected() -> None:
    value = receipt()
    value["reviewed_files"] = value["reviewed_files"][:-1]
    with pytest.raises(RuntimeError, match="exact published artifact set"):
        validate(value)


def test_wrong_workledger_revision_is_rejected() -> None:
    value = receipt()
    value["workledger_revision_id"] = "rev_wrong"
    with pytest.raises(RuntimeError, match="WorkLedger revision identity mismatch"):
        validate(value)


def test_storyboard_rejects_final_pass_decision() -> None:
    value = receipt("0005-027")
    value["decision"] = "PASS"
    with pytest.raises(RuntimeError, match="unsupported decision"):
        validate(value, step_id="0005-027")
