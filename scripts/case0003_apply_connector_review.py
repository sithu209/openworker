"""Apply a ChatGPT review grounded by the connected Google Drive.

PASS accepts the exact immutable review revision, but does not mark WorkLedger as
delivered. The connector receipt must bind to the local-first immutable review ZIP,
the exact bundle manifest, and connector-observed Google Drive folder/file IDs.
"""
from __future__ import annotations
import argparse, hashlib, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from coworker.review_cycle import ReviewCycle
from coworker.review_gap import apply_review_finding
from coworker.work_ledger import WorkLedger

JOB_CODE = "OWJ-20260816030152-03D90D"


def _load(path: Path, label: str) -> dict:
    if not path.is_file() or path.stat().st_size <= 0:
        raise RuntimeError(f"{label} unavailable: {path}")
    value=json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value,dict):
        raise RuntimeError(f"{label} must be a JSON object")
    return value


def _sha256(path: Path) -> str:
    h=hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024*1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main(argv=None):
    p=argparse.ArgumentParser(); p.add_argument("--workspace",required=True); p.add_argument("--revision-id",required=True); p.add_argument("--receipt",required=True); a=p.parse_args(argv)
    workspace=Path(a.workspace).expanduser().resolve(); revision_id=str(a.revision_id).strip(); receipt_path=Path(a.receipt).expanduser().resolve(); receipt=_load(receipt_path,"connector review receipt")
    if str(receipt.get("revision_id") or "").strip()!=revision_id: raise RuntimeError("connector review receipt revision_id mismatch")
    if str(receipt.get("transport") or "").strip()!="google-drive-connector": raise RuntimeError("connector review receipt transport mismatch")

    prepare=_load(workspace/"acceptance"/"openworker-final"/f"drive-review-prepare-{revision_id}.json","Drive review prepare receipt")
    if prepare.get("schema_version")!="openworker-case0003-drive-review-prepare/v2": raise RuntimeError("Drive review prepare v2 required")
    if str(prepare.get("revision_id") or "")!=revision_id or str(prepare.get("status") or "")!="WAITING_DRIVE_REVIEW": raise RuntimeError("Drive review prepare identity/state mismatch")
    local_zip=Path(str(prepare.get("review_zip_path") or "")).expanduser().resolve()
    local_zip_sha=str(prepare.get("review_zip_sha256") or "").strip().lower()
    if not local_zip.is_file() or local_zip.stat().st_size<=0 or _sha256(local_zip)!=local_zip_sha: raise RuntimeError("local immutable review ZIP missing or changed")

    cloud=receipt.get("cloud_publication") or {}
    if not isinstance(cloud,dict): raise RuntimeError("cloud_publication must be an object")
    for key in ("drive_revision_folder_id","drive_zip_file_id","review_zip_sha256","bundle_manifest_sha256"):
        if not str(cloud.get(key) or "").strip(): raise RuntimeError(f"connector review receipt missing cloud_publication.{key}")
    if str(cloud.get("review_zip_sha256") or "").lower()!=local_zip_sha: raise RuntimeError("connector-reviewed Drive ZIP SHA does not match local immutable ZIP")
    if str(cloud.get("bundle_manifest_sha256") or "").lower()!=str(receipt.get("bundle_manifest_sha256") or "").lower(): raise RuntimeError("cloud publication manifest SHA does not match review receipt")
    if str(prepare.get("bundle_manifest_sha256") or "").lower()!=str(receipt.get("bundle_manifest_sha256") or "").lower(): raise RuntimeError("connector review is stale for current prepared bundle")

    request=_load(workspace/".openworker"/"reviews"/revision_id/"review-request.json","review request")
    ledger=WorkLedger(workspace/".openworker"/"work-ledger.sqlite")
    try:
        work=ledger.get_work_by_code(JOB_CODE); revision=ledger.get_revision(revision_id)
        if revision["work_id"]!=work["work_id"]: raise RuntimeError("revision does not belong to Case 0003 work")
        result=apply_review_finding(ReviewCycle(workspace),ledger,revision_id,receipt,allowed_parameter_keys=request.get("allowed_parameter_keys") or [],current_parameters=request.get("current_parameters") or {})
        verdict=str(result.get("verdict") or "").upper(); accepted_revision_id=""
        if verdict=="PASS":
            accepted_revision_id=ledger.accept_revision(revision_id)["revision_id"]
            status="ACCEPTED_PENDING_FINALIZE"
        elif verdict=="TUNE": status="TUNING_REQUIRED"
        else: status="TOOL_GAP_REWORK_REQUIRED" if result.get("finding_type")=="TOOL_GAP" else "REWORK_REQUIRED"
        output={
            "schema_version":"openworker-case0003-connector-review-apply/v3",
            "case_id":"0003",
            "revision_id":revision_id,
            "verdict":str(receipt.get("verdict") or "").upper(),
            "finding_type":result.get("finding_type",receipt.get("verdict")),
            "status":status,
            "accepted_revision_id":accepted_revision_id,
            "delivered_revision_id":"",
            "next_revision_id":result.get("next_revision_id",""),
            "owning_repo":result.get("owning_repo",""),
            "gap_capability":result.get("gap_capability",""),
            "verification_plan":result.get("verification_plan",[]),
            "bundle_manifest_sha256":receipt.get("bundle_manifest_sha256",""),
            "review_zip_sha256":local_zip_sha,
            "cloud_publication":cloud,
            "ledger":ledger.snapshot(work["work_id"]),
        }
        out=workspace/"acceptance"/"openworker-final"/f"connector-review-apply-{revision_id}.json"; out.parent.mkdir(parents=True,exist_ok=True); payload=json.dumps(output,ensure_ascii=False,indent=2,default=str); out.write_text(payload,encoding="utf-8")
        latest=workspace/"acceptance"/"openworker-final"/"connector-review-apply.json"; latest.write_text(payload,encoding="utf-8")
        print(json.dumps(output,ensure_ascii=False,sort_keys=True,default=str)); return 0 if verdict=="PASS" else 4
    finally: ledger.close()


if __name__=="__main__":
    try: raise SystemExit(main())
    except Exception as exc: print(f"CASE0003_CONNECTOR_REVIEW_APPLY_FAIL {exc}",file=sys.stderr); raise
