"""LLM-facing artifact review and parameter tuning governance for OpenWorker.

Google Drive is only a temporary review exchange. WorkLedger remains the durable
authority for revision history, reviewed artifact SHA, parameter deltas and verdicts.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from .work_ledger import WorkLedger

_REVIEW_VERDICTS = {"PASS", "TUNE", "FAIL"}
DEFAULT_DRIVE_FOLDER_ID = "1A4BnZEcFe2WIhcperRd4QSpxoSUN_ARR"
DEFAULT_DRIVE_FOLDER_NAME = "OpenWorker-ChatGPT-Review-TEMP"


class ReviewCycleError(RuntimeError):
    pass


@dataclass(frozen=True)
class ReviewArtifact:
    logical_name: str
    path: Path


class ReviewCycle:
    """Build review bundles and project structured LLM review into WorkLedger."""

    def __init__(self, workspace: str | Path, *, drive_folder_id: str = DEFAULT_DRIVE_FOLDER_ID) -> None:
        self.workspace = Path(workspace).expanduser().resolve()
        self.openworker_dir = self.workspace / ".openworker"
        self.review_dir = self.openworker_dir / "reviews"
        self.drive_folder_id = str(drive_folder_id).strip()

    def build_bundle(
        self,
        ledger: WorkLedger,
        revision_id: str,
        *,
        artifacts: Sequence[ReviewArtifact],
        review_dimensions: Sequence[str],
        current_parameters: Mapping[str, Any],
        allowed_parameter_keys: Sequence[str],
        capability_id: str,
        owning_repo: str,
        max_total_bytes: int = 512 * 1024 * 1024,
    ) -> Path:
        revision = ledger.get_revision(revision_id)
        bundle_root = self.review_dir / revision_id
        staging_parent = self.review_dir.parent if self.review_dir.parent.exists() else self.openworker_dir
        staging_parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=f"{revision_id}-", dir=str(staging_parent)))
        payload_dir = staging / "artifacts"
        payload_dir.mkdir(parents=True, exist_ok=True)

        manifest_items: list[dict[str, Any]] = []
        total = 0
        seen_names: set[str] = set()
        try:
            for item in artifacts:
                logical = str(item.logical_name).strip()
                if not logical or logical in seen_names:
                    raise ReviewCycleError(f"invalid/duplicate review artifact logical_name: {logical!r}")
                seen_names.add(logical)
                source = Path(item.path).expanduser().resolve()
                if not source.is_file() or source.stat().st_size <= 0:
                    raise ReviewCycleError(f"review artifact missing/empty: {source}")
                size = source.stat().st_size
                total += size
                if total > int(max_total_bytes):
                    raise ReviewCycleError(f"review bundle exceeds max_total_bytes={max_total_bytes}")
                digest = _sha256(source)
                safe_name = _safe_name(logical) + source.suffix.lower()
                dest = payload_dir / safe_name
                shutil.copy2(source, dest)
                if _sha256(dest) != digest:
                    raise ReviewCycleError(f"review artifact copy SHA mismatch: {logical}")
                manifest_items.append(
                    {
                        "logical_name": logical,
                        "filename": str(Path("artifacts") / safe_name).replace("\\", "/"),
                        "sha256": digest,
                        "size_bytes": size,
                    }
                )

            request = {
                "schema_version": "openworker-review-request/v1",
                "revision_id": revision_id,
                "parent_revision_id": revision.get("parent_revision_id") or "",
                "revision_no": revision.get("revision_no"),
                "review_dimensions": [str(v) for v in review_dimensions if str(v).strip()],
                "capability_id": str(capability_id).strip(),
                "owning_repo": str(owning_repo).strip(),
                "current_parameters": dict(current_parameters),
                "allowed_parameter_keys": sorted({str(v).strip() for v in allowed_parameter_keys if str(v).strip()}),
                "drive_folder_id": self.drive_folder_id,
                "artifacts": manifest_items,
            }
            (staging / "review-request.json").write_text(
                json.dumps(request, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
            )
            manifest = {
                "schema_version": "openworker-review-bundle/v1",
                "revision_id": revision_id,
                "total_bytes": total,
                "files": manifest_items,
                "review_request_sha256": _sha256(staging / "review-request.json"),
            }
            (staging / "manifest.json").write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
            )
            if bundle_root.exists():
                raise ReviewCycleError(f"review bundle already exists for revision: {revision_id}")
            bundle_root.parent.mkdir(parents=True, exist_ok=True)
            staging.replace(bundle_root)
            return bundle_root
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise

    def resolve_drive_sync_root(self, configured: str | Path | None = None) -> Path:
        """Resolve exactly one bounded Google Drive Desktop review folder.

        Explicit configuration wins. Without it, only common non-recursive candidate
        locations are inspected. Ambiguous matches fail closed so artifacts cannot be
        copied to the wrong Google account or mirrored Drive.
        """
        explicit = str(configured or os.environ.get("OPENWORKER_REVIEW_DRIVE_ROOT") or "").strip()
        if explicit:
            root = Path(explicit).expanduser().resolve()
            if not root.is_dir():
                raise ReviewCycleError(f"Google Drive sync root unavailable: {root}")
            return root

        folder = DEFAULT_DRIVE_FOLDER_NAME
        candidates: list[Path] = []
        home = Path.home()
        home_forms = [
            home / folder,
            home / "My Drive" / folder,
            home / "Google Drive" / "My Drive" / folder,
            home / "我的雲端硬碟" / folder,
            home / "Google Drive" / "我的雲端硬碟" / folder,
        ]
        candidates.extend(home_forms)

        if os.name == "nt":
            for letter in "CDEFGHIJKLMNOPQRSTUVWXYZ":
                base = Path(f"{letter}:\\")
                candidates.extend(
                    [
                        base / folder,
                        base / "My Drive" / folder,
                        base / "我的雲端硬碟" / folder,
                    ]
                )

        found: list[Path] = []
        seen: set[str] = set()
        for candidate in candidates:
            try:
                if not candidate.is_dir():
                    continue
                resolved = candidate.resolve()
            except OSError:
                continue
            key = os.path.normcase(str(resolved))
            if key not in seen:
                seen.add(key)
                found.append(resolved)

        if not found:
            raise ReviewCycleError(
                "Google Drive review sync folder not found; set OPENWORKER_REVIEW_DRIVE_ROOT "
                f"or mirror {DEFAULT_DRIVE_FOLDER_NAME!r} with Google Drive for desktop"
            )
        if len(found) > 1:
            raise ReviewCycleError(
                "multiple Google Drive review sync folders found; set OPENWORKER_REVIEW_DRIVE_ROOT explicitly: "
                + "; ".join(str(path) for path in found)
            )
        return found[0]

    def handoff_to_drive_sync(
        self,
        bundle_root: str | Path,
        *,
        drive_sync_root: str | Path | None = None,
        work_code: str,
    ) -> Path:
        """Atomically copy a bundle into the dedicated Drive review folder."""
        source = Path(bundle_root).expanduser().resolve()
        if not source.is_dir():
            raise ReviewCycleError(f"review bundle unavailable: {source}")
        root = self.resolve_drive_sync_root(drive_sync_root)
        revision_id = source.name
        target_parent = root / _safe_name(work_code)
        target = target_parent / revision_id
        if target.exists():
            raise ReviewCycleError(f"Drive review target already exists: {target}")
        target_parent.mkdir(parents=True, exist_ok=True)
        staging = target_parent / f".{revision_id}.uploading"
        if staging.exists():
            shutil.rmtree(staging)
        shutil.copytree(source, staging)
        _verify_tree_same(source, staging)
        staging.replace(target)
        return target

    def apply_receipt(
        self,
        ledger: WorkLedger,
        revision_id: str,
        receipt: Mapping[str, Any],
        *,
        allowed_parameter_keys: Sequence[str],
        current_parameters: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Record a model verdict and create the next governed revision when needed."""
        verdict = str(receipt.get("verdict") or "").strip().upper()
        if verdict not in _REVIEW_VERDICTS:
            raise ReviewCycleError(f"unsupported review verdict: {verdict!r}")
        revision = ledger.get_revision(revision_id)
        if revision["status"] not in {"open", "executing", "verifying", "blocked"}:
            raise ReviewCycleError(f"cannot review immutable revision status={revision['status']}")

        receipt_path = self.review_dir / revision_id / "llm-review-receipt.json"
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        if receipt_path.exists():
            raise ReviewCycleError(f"LLM review receipt already exists for revision: {revision_id}")
        normalized = dict(receipt)
        normalized["schema_version"] = "openworker-llm-review-receipt/v1"
        normalized["verdict"] = verdict
        normalized["revision_id"] = revision_id
        receipt_path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        ledger.add_file_artifact(
            revision_id,
            logical_name="llm-review-receipt.json",
            path=receipt_path,
            provenance={"reviewer": "LLM", "verdict": verdict},
            verification_status="passed",
        )

        reviewed = normalized.get("reviewed_artifacts") or []
        ledger.set_check(
            revision_id,
            name="LLM Semantic Review",
            status="passed" if verdict == "PASS" else "failed",
            required=True,
            evidence={"verdict": verdict, "reviewed_artifacts": reviewed, "summary": normalized.get("summary", "")},
            reason=str(normalized.get("summary") or ""),
        )
        if verdict == "PASS":
            return {"verdict": verdict, "revision_id": revision_id, "next_revision_id": "", "parameters": dict(current_parameters)}

        if verdict == "FAIL":
            owner = str(normalized.get("owning_repo") or "").strip()
            reason = str(normalized.get("summary") or "LLM semantic review failed").strip()
            ledger.request_rework(
                revision_id,
                reason=reason,
                gap_owner_repo=owner,
                verification_plan=[str(v) for v in normalized.get("verification_plan", []) if str(v).strip()],
            )
            return {"verdict": verdict, "revision_id": revision_id, "next_revision_id": "", "parameters": dict(current_parameters)}

        allow = {str(v).strip() for v in allowed_parameter_keys if str(v).strip()}
        changes = normalized.get("parameter_changes") or []
        if not isinstance(changes, list) or not changes:
            raise ReviewCycleError("TUNE verdict requires non-empty parameter_changes")
        next_parameters = dict(current_parameters)
        deltas: list[dict[str, Any]] = []
        for change in changes:
            if not isinstance(change, Mapping):
                raise ReviewCycleError("parameter_changes entries must be objects")
            key = str(change.get("parameter") or "").strip()
            if key not in allow:
                raise ReviewCycleError(f"LLM attempted non-allowlisted parameter: {key}")
            before = next_parameters.get(key)
            declared_before = change.get("before", before)
            if declared_before != before:
                raise ReviewCycleError(f"parameter before-value mismatch for {key}: expected {before!r}, got {declared_before!r}")
            after = change.get("after")
            if after == before:
                raise ReviewCycleError(f"parameter change is a no-op: {key}")
            next_parameters[key] = after
            deltas.append(
                {
                    "parameter": key,
                    "before": before,
                    "after": after,
                    "reason": str(change.get("reason") or "").strip(),
                    "expected_effect": str(change.get("expected_effect") or "").strip(),
                }
            )

        ledger.set_revision_status(revision_id, "blocked", reason="LLM requested parameter tuning")
        child = ledger.open_revision(
            revision["work_id"],
            kind="tuning",
            goal="LLM-guided parameter tuning rerun",
            parent_revision_id=revision_id,
            plan={
                "revision_role": "tuning",
                "source_review_revision_id": revision_id,
                "parameter_delta": deltas,
                "parameters": next_parameters,
            },
            reason="LLM requested parameter tuning",
        )
        return {
            "verdict": verdict,
            "revision_id": revision_id,
            "next_revision_id": child["revision_id"],
            "parameters": next_parameters,
            "parameter_delta": deltas,
        }


def _safe_name(value: str) -> str:
    text = "".join(c if c.isalnum() or c in "-_." else "-" for c in str(value).strip())
    text = text.strip("-.")
    if not text:
        raise ReviewCycleError("safe name is empty")
    return text[:120]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_tree_same(source: Path, target: Path) -> None:
    source_files = sorted(p.relative_to(source) for p in source.rglob("*") if p.is_file())
    target_files = sorted(p.relative_to(target) for p in target.rglob("*") if p.is_file())
    if source_files != target_files:
        raise ReviewCycleError("Drive handoff file set mismatch")
    for rel in source_files:
        if _sha256(source / rel) != _sha256(target / rel):
            raise ReviewCycleError(f"Drive handoff SHA mismatch: {rel}")


__all__ = [
    "DEFAULT_DRIVE_FOLDER_ID",
    "DEFAULT_DRIVE_FOLDER_NAME",
    "ReviewArtifact",
    "ReviewCycle",
    "ReviewCycleError",
]
