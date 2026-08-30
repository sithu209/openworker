from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from coworker.case_worklist import CaseWorklistError
from coworker.case_worklist_runtime import CaseWorklistRuntime

_ACTION = "presentation.openmaic"
_STAGE = {
    "0002-025": {
        "path": "storyboard_pptx",
        "manifest": "storyboard_manifest",
        "sha256": "storyboard_pptx_sha256",
        "media": "image_count",
        "require_media": False,
    },
    "0002-055": {
        "path": "illustrated_storyboard_pptx",
        "manifest": "illustrated_storyboard_manifest",
        "sha256": "illustrated_storyboard_sha256",
        "media": "bound_image_count",
        "require_media": True,
    },
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _bounded_path(workspace: Path, value: Any, *, field: str) -> Path:
    raw = _text(value)
    if not raw:
        raise CaseWorklistError(f"OpenMAIC receipt missing {field}")
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = workspace / candidate
    resolved = candidate.resolve()
    try:
        resolved.relative_to(workspace)
    except ValueError as exc:
        raise CaseWorklistError(f"OpenMAIC {field} escapes workspace: {resolved}") from exc
    return resolved


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _physical_media_count(pptx: Path) -> int:
    try:
        with zipfile.ZipFile(pptx, "r") as archive:
            return sum(
                1
                for name in archive.namelist()
                if name.startswith("ppt/media/") and not name.endswith("/")
            )
    except zipfile.BadZipFile as exc:
        raise CaseWorklistError(f"OpenMAIC PPTX is not a valid OOXML ZIP: {pptx}") from exc


def validate_receipt(
    workspace_root: str | Path,
    assigned_host: str,
    step_id: str,
    receipt: dict[str, Any],
    *,
    expected_run_id: str | int | None = None,
) -> dict[str, Any]:
    cfg = _STAGE.get(step_id)
    if cfg is None:
        raise CaseWorklistError(f"OpenMAIC receipt is not valid for step {step_id!r}")
    if _text(receipt.get("tool")) != _ACTION:
        raise CaseWorklistError("OpenMAIC receipt tool mismatch")
    if _text(receipt.get("status")).lower() != "succeeded":
        raise CaseWorklistError("OpenMAIC receipt is not succeeded")

    action = receipt.get("action")
    if not isinstance(action, dict):
        raise CaseWorklistError("OpenMAIC receipt action authority is missing")
    receipt_run_id = _text(action.get("run_id"))
    if not receipt_run_id:
        raise CaseWorklistError("OpenMAIC receipt action.run_id is missing")
    if expected_run_id is not None and receipt_run_id != _text(expected_run_id):
        raise CaseWorklistError(
            f"OpenMAIC receipt run mismatch expected={_text(expected_run_id)!r} actual={receipt_run_id!r}"
        )

    runner = receipt.get("runner")
    if not isinstance(runner, dict):
        raise CaseWorklistError("OpenMAIC receipt runner is missing")
    actual_host = _text(runner.get("computer_name"))
    if not actual_host or actual_host.casefold() != _text(assigned_host).casefold():
        raise CaseWorklistError(
            f"OpenMAIC host mismatch expected={assigned_host!r} actual={actual_host!r}"
        )

    artifact = receipt.get("artifact")
    if not isinstance(artifact, dict):
        raise CaseWorklistError("OpenMAIC receipt artifact is missing")
    try:
        slide_count = int(artifact.get("slide_count", 0))
        receipt_media_count = int(artifact.get("media_count", -1))
    except (TypeError, ValueError) as exc:
        raise CaseWorklistError("OpenMAIC artifact counts are invalid") from exc
    if slide_count <= 0:
        raise CaseWorklistError("OpenMAIC slide_count must be positive")
    if receipt_media_count < 0:
        raise CaseWorklistError("OpenMAIC media_count is missing")

    receipt_sha = _text(artifact.get("sha256")).lower()
    if len(receipt_sha) != 64 or any(ch not in "0123456789abcdef" for ch in receipt_sha):
        raise CaseWorklistError("OpenMAIC artifact sha256 is invalid")

    workspace = Path(workspace_root).resolve()
    pptx = _bounded_path(workspace, artifact.get("path"), field="artifact.path")
    manifest = _bounded_path(workspace, receipt.get("manifest"), field="manifest")
    if not pptx.is_file() or pptx.stat().st_size <= 0:
        raise CaseWorklistError(f"OpenMAIC physical PPTX missing/empty: {pptx}")
    if not manifest.is_file() or manifest.stat().st_size <= 0:
        raise CaseWorklistError(f"OpenMAIC physical manifest missing/empty: {manifest}")

    physical_sha = _sha256(pptx)
    if physical_sha != receipt_sha:
        raise CaseWorklistError(
            f"OpenMAIC physical PPTX sha256 mismatch receipt={receipt_sha} physical={physical_sha}"
        )
    physical_media_count = _physical_media_count(pptx)
    if physical_media_count != receipt_media_count:
        raise CaseWorklistError(
            f"OpenMAIC media_count mismatch receipt={receipt_media_count} physical={physical_media_count}"
        )
    if cfg["require_media"] and physical_media_count <= 0:
        raise CaseWorklistError("illustrated storyboard requires media_count > 0")
    if not cfg["require_media"] and physical_media_count != 0:
        raise CaseWorklistError("text-only storyboard requires media_count == 0")

    try:
        manifest_json = json.loads(manifest.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        raise CaseWorklistError(f"OpenMAIC manifest is not valid JSON: {manifest}") from exc
    if not isinstance(manifest_json, dict) or _text(manifest_json.get("status")).lower() != "succeeded":
        raise CaseWorklistError("OpenMAIC manifest status is not succeeded")
    manifest_artifact = manifest_json.get("artifact")
    if not isinstance(manifest_artifact, dict):
        raise CaseWorklistError("OpenMAIC manifest artifact is missing")
    manifest_sha = _text(manifest_artifact.get("sha256")).lower()
    if manifest_sha != physical_sha:
        raise CaseWorklistError(
            f"OpenMAIC manifest sha256 mismatch manifest={manifest_sha} physical={physical_sha}"
        )
    try:
        manifest_slides = int(manifest_artifact.get("slide_count", 0))
    except (TypeError, ValueError) as exc:
        raise CaseWorklistError("OpenMAIC manifest slide_count is invalid") from exc
    if manifest_slides != slide_count or manifest_slides <= 0:
        raise CaseWorklistError(
            f"OpenMAIC slide_count mismatch receipt={slide_count} manifest={manifest_slides}"
        )

    return {
        cfg["path"]: str(pptx),
        cfg["manifest"]: str(manifest),
        cfg["sha256"]: physical_sha,
        "slide_count": slide_count,
        "reopen_receipt": receipt,
        cfg["media"]: physical_media_count,
    }


def apply_receipt(
    workspace_root: str | Path,
    step_id: str,
    execution_id: str,
    receipt: dict[str, Any],
    *,
    expected_run_id: str | int | None = None,
):
    runtime = CaseWorklistRuntime(workspace_root)
    current = runtime.load()
    if current.case_id != "0002":
        raise CaseWorklistError(f"case mismatch: {current.case_id!r}")
    evidence = validate_receipt(
        current.workspace_root,
        current.assigned_host,
        step_id,
        receipt,
        expected_run_id=expected_run_id,
    )
    return runtime.accept_action_evidence(
        step_id,
        _ACTION,
        execution_id=execution_id,
        evidence=evidence,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace-root", required=True)
    parser.add_argument("--step-id", required=True, choices=sorted(_STAGE))
    parser.add_argument("--execution-id", required=True)
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--expected-run-id")
    args = parser.parse_args()

    receipt_path = Path(args.receipt).resolve()
    raw = json.loads(receipt_path.read_text(encoding="utf-8-sig"))
    if not isinstance(raw, dict):
        raise CaseWorklistError("OpenMAIC receipt root must be an object")
    worklist = apply_receipt(
        args.workspace_root,
        args.step_id,
        args.execution_id,
        raw,
        expected_run_id=args.expected_run_id,
    )
    data = worklist.as_dict()
    print(json.dumps(data, ensure_ascii=False, indent=2))
    print(
        f"CASE0002_OPENMAIC_RECEIPT_APPLIED step={args.step_id} "
        f"next={data['canonical_next_step_id']} receipt={receipt_path}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"CASE0002_OPENMAIC_RECEIPT_FAIL: {exc}")
        raise SystemExit(2)
