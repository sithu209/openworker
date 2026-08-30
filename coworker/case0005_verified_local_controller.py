"""Canonical Case 0005 controller gated by current local-supervisor health.

All business fanout is owned by go-tool :8848. OpenWorker is used only as the
resident process/progress kernel and runs one lightweight coordinator per
fanout group. Reviewable artifacts are published by an allowlisted local
capability through Google Drive API so ChatGPT can fetch the physical files via
its Drive connector. There is no GitHub Actions fallback or GitHub artifact
transport.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .case0005_artifact_publish_acceptance import Case0005ArtifactPublishAcceptanceMixin
from .case0005_lifecycle import Case0005LifecycleMixin
from .case0005_coordinator_recovery import Case0005CoordinatorRecoveryMixin
from .case0005_direct_queue_fanout import Case0005DirectQueueFanoutMixin
from .case0005_true_local_controller import TrueLocalCase0005Controller
from .case_worklist import CaseWorklistError

_SUPERVISOR_STATUS_URL = "http://127.0.0.1:8848/api/execution/local-supervisor/status"
_CANONICAL_MODULE = "coworker.case0005_verified_local_controller"
_ARTIFACT_PUBLISH_ACTION = "openworker.case.publish-artifacts"
_REVIEW_GATE_ACTION = "openworker.review.await-drive"


class VerifiedLocalCase0005Controller(
    Case0005ArtifactPublishAcceptanceMixin,
    Case0005LifecycleMixin,
    Case0005CoordinatorRecoveryMixin,
    Case0005DirectQueueFanoutMixin,
    TrueLocalCase0005Controller,
):
    def _require_verified_local_supervisor(self, operation: str) -> dict:
        try:
            request = Request(_SUPERVISOR_STATUS_URL, method="GET")
            with urlopen(request, timeout=8) as response:
                payload = response.read(4 * 1024 * 1024)
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            self._append_ledger("local_supervisor_operational_check_failed",operation=operation,status_url=_SUPERVISOR_STATUS_URL,reason=f"local supervisor status endpoint unavailable: {exc}",execution_route="blocked",github_action_fallback_allowed=False)
            raise CaseWorklistError(f"true local supervisor status endpoint unavailable: {exc}") from exc
        try: value=json.loads(payload.decode("utf-8"))
        except Exception as exc:
            self._append_ledger("local_supervisor_operational_check_failed",operation=operation,status_url=_SUPERVISOR_STATUS_URL,reason=f"invalid status JSON: {exc}",execution_route="blocked",github_action_fallback_allowed=False)
            raise CaseWorklistError("true local supervisor status returned invalid JSON") from exc
        if not isinstance(value,dict): raise CaseWorklistError("true local supervisor status response must be an object")
        status=str(value.get("status","")).strip();verification=value.get("verification");verification_status=str(verification.get("status","")).strip() if isinstance(verification,dict) else "";claim_slots=int(value.get("fresh_claim_slot_count",0) or 0);executor_slots=int(value.get("fresh_executor_slot_count",0) or 0);operational=bool(value.get("operational"));route_label=str(value.get("route_label","")).strip();github_used=bool(value.get("github_action_used_for_business_execution"))
        if status!="OPERATIONAL" or not operational or verification_status!="REAL_VERIFIED" or claim_slots<4 or executor_slots<4 or route_label!="LOCAL_SUPERVISOR" or github_used:
            self._append_ledger("local_supervisor_operational_check_failed",operation=operation,status_url=_SUPERVISOR_STATUS_URL,supervisor_status=status or "UNKNOWN",verification_status=verification_status or "UNKNOWN",fresh_claim_slot_count=claim_slots,fresh_executor_slot_count=executor_slots,route_label=route_label,supervisor=value,execution_route="blocked",github_action_fallback_allowed=False)
            raise CaseWorklistError("true local supervisor is not OPERATIONAL with four live claim and executor slots; "+f"status={status or 'UNKNOWN'} verification={verification_status or 'UNKNOWN'} claim_slots={claim_slots} executor_slots={executor_slots}; business dispatch is blocked and GitHub Actions fallback is forbidden")
        self._append_ledger("local_supervisor_operational_check_passed",operation=operation,status_url=_SUPERVISOR_STATUS_URL,supervisor_status=status,verification_status=verification_status,fresh_claim_slot_count=claim_slots,fresh_executor_slot_count=executor_slots,active_slots=int(value.get("active_slots",0) or 0),free_slots=int(value.get("free_slots",0) or 0),execution_route="local_supervisor",github_action_used_for_business_execution=False)
        return value

    def bootstrap(self, manifest_path, spec_path):
        self._require_verified_local_supervisor("bootstrap")
        return super().bootstrap(manifest_path, spec_path)

    def dispatch_ready(self):
        self._require_verified_local_supervisor("dispatch")
        recovered=self._resume_queue_owned_coordinators();result=super().dispatch_ready()
        if recovered: result=dict(result);result["recovered_queue_coordinators"]=recovered
        return result

    @staticmethod
    def _safe_single_component(value: str, label: str) -> str:
        value = str(value or "").strip()
        if not value or value in {".", ".."} or "/" in value or "\\" in value:
            raise CaseWorklistError(f"{label} must be one safe path component")
        return value

    def _claim_inputs(self, worklist, step, action: str, spec):
        if action == _ARTIFACT_PUBLISH_ACTION:
            if step.step_id == "0005-026":
                artifacts = ["presentation/storyboard-text-only.pptx"]
                label = "text-storyboard"
                revision_id = f"case0005-{label}-approval-r{worklist.revision:06d}"
            elif step.step_id == "0005-056":
                artifacts = ["presentation/storyboard-illustrated.pptx"]
                label = "illustrated-storyboard"
                revision_id = f"case0005-{label}-approval-r{worklist.revision:06d}"
            elif step.step_id == "0005-090":
                revision = self._safe_single_component(
                    str(worklist.step("0005-080").evidence.get("revision_id", "")),
                    "WorkLedger revision_id",
                )
                artifacts = [
                    "final/final.mp4",
                    "final/review-contact-sheet.jpg",
                    f".openworker/revisions/{revision}/manifest.json",
                ]
                label = "final-review"
                revision_id = f"case0005-{label}-{revision}"
            else:
                return super()._claim_inputs(worklist, step, action, spec)
            return {
                "workspace_root": str(self.workspace),
                "assigned_host": worklist.assigned_host,
                "case_id": worklist.case_id,
                "step_id": step.step_id,
                "revision_id": revision_id,
                "work_code": f"CASE0005-{label.upper()}",
                "artifacts": artifacts,
                "run_id": revision_id,
            }
        return super()._claim_inputs(worklist, step, action, spec)

    def _job_payload(self, worklist, step, action: str, execution_id: str, claim_path: Path) -> dict:
        python=sys.executable or "python";argv=[python,"-m",_CANONICAL_MODULE,"run-step","--workspace",str(self.workspace),"--step-id",step.step_id,"--action-id",action,"--execution-id",execution_id,"--claim",str(claim_path)]
        timeout_sec=86400 if action==_REVIEW_GATE_ACTION else 3600
        return {"job_id":execution_id,"dispatch_id":"verified-local-controller-"+execution_id,"machine":worklist.assigned_host,"priority":100 if step.kind in {"fanout","join"} else 80,"command":subprocess.list2cmdline(argv),"cwd":str(self.openworker_root),"workspace_root":str(self.workspace),"env":self._localexec_env(),"timeout_sec":timeout_sec,"locks":[f"case:{worklist.case_id}:step:{step.step_id}"]}

    def _image_child_payload(self,*,worklist,step_id:str,group_id:str,child_id:str,asset_id:str,role:str,claim_path:Path,manifest_path:Path)->dict:
        python=sys.executable or "python";argv=[python,"-m",_CANONICAL_MODULE,"run-image-asset","--workspace",str(self.workspace),"--step-id",step_id,"--group-execution-id",group_id,"--child-job-id",child_id,"--asset-id",asset_id,"--role",role,"--claim",str(claim_path),"--fanout-manifest",str(manifest_path)]
        return {"job_id":child_id,"dispatch_id":"verified-local-controller-"+child_id,"machine":worklist.assigned_host,"priority":100,"command":subprocess.list2cmdline(argv),"cwd":str(self.openworker_root),"workspace_root":str(self.workspace),"env":self._localexec_env(),"timeout_sec":2100,"locks":[f"case:{worklist.case_id}:image-asset:{self._safe_id(asset_id)}"]}

    def _video_child_payload(self,*,worklist,group_id:str,child_id:str,shot_id:str,claim_path:Path,manifest_path:Path)->dict:
        python=sys.executable or "python";argv=[python,"-m",_CANONICAL_MODULE,"run-video-shot","--workspace",str(self.workspace),"--group-execution-id",group_id,"--child-job-id",child_id,"--shot-id",shot_id,"--claim",str(claim_path),"--fanout-manifest",str(manifest_path)]
        return {"job_id":child_id,"dispatch_id":"verified-local-controller-"+child_id,"machine":worklist.assigned_host,"priority":100,"command":subprocess.list2cmdline(argv),"cwd":str(self.openworker_root),"workspace_root":str(self.workspace),"env":self._localexec_env(),"timeout_sec":2100,"locks":[f"case:{worklist.case_id}:video-shot:{self._safe_id(shot_id)}"]}


def _parser()->argparse.ArgumentParser:
    parser=argparse.ArgumentParser(description="Case 0005 OPERATIONAL local controller");parser.add_argument("--node-url",default="http://127.0.0.1:8787");sub=parser.add_subparsers(dest="command",required=True)
    bootstrap=sub.add_parser("bootstrap");bootstrap.add_argument("--workspace",required=True);bootstrap.add_argument("--manifest",required=True);bootstrap.add_argument("--spec",required=True)
    dispatch=sub.add_parser("dispatch");dispatch.add_argument("--workspace",required=True);dispatch.add_argument("--spec")
    run=sub.add_parser("run-step");run.add_argument("--workspace",required=True);run.add_argument("--spec");run.add_argument("--step-id",required=True);run.add_argument("--action-id",required=True);run.add_argument("--execution-id",required=True);run.add_argument("--claim",required=True)
    image=sub.add_parser("run-image-asset");image.add_argument("--workspace",required=True);image.add_argument("--step-id",required=True);image.add_argument("--group-execution-id",required=True);image.add_argument("--child-job-id",required=True);image.add_argument("--asset-id",required=True);image.add_argument("--role",required=True);image.add_argument("--claim",required=True);image.add_argument("--fanout-manifest",required=True)
    video=sub.add_parser("run-video-shot");video.add_argument("--workspace",required=True);video.add_argument("--spec");video.add_argument("--group-execution-id",required=True);video.add_argument("--child-job-id",required=True);video.add_argument("--shot-id",required=True);video.add_argument("--claim",required=True);video.add_argument("--fanout-manifest",required=True)
    watch_image=sub.add_parser("watch-image-fanout");watch_image.add_argument("--workspace",required=True);watch_image.add_argument("--spec");watch_image.add_argument("--fanout-manifest",required=True)
    watch_video=sub.add_parser("watch-video-fanout");watch_video.add_argument("--workspace",required=True);watch_video.add_argument("--spec");watch_video.add_argument("--fanout-manifest",required=True)
    return parser


def main()->int:
    args=_parser().parse_args();controller=VerifiedLocalCase0005Controller(args.workspace,node_url=args.node_url,spec_path=getattr(args,"spec",None))
    try:
        if args.command=="bootstrap": result=controller.bootstrap(args.manifest,args.spec)
        elif args.command=="dispatch": result=controller.dispatch_ready()
        elif args.command=="run-step": result=controller.run_step(step_id=args.step_id,action_id=args.action_id,execution_id=args.execution_id,claim_path=args.claim)
        elif args.command=="run-image-asset": result=controller.run_image_asset(step_id=args.step_id,group_execution_id=args.group_execution_id,child_job_id=args.child_job_id,asset_id=args.asset_id,role=args.role,claim_path=args.claim,fanout_manifest=args.fanout_manifest)
        elif args.command=="run-video-shot": result=controller.run_video_shot(group_execution_id=args.group_execution_id,child_job_id=args.child_job_id,shot_id=args.shot_id,claim_path=args.claim,fanout_manifest=args.fanout_manifest)
        elif args.command=="watch-image-fanout": result=controller.watch_image_fanout(args.fanout_manifest)
        else: result=controller.watch_video_fanout(args.fanout_manifest)
    except Exception as exc:
        try: controller._append_ledger("controller_command_failed",command=args.command,error=str(exc))
        except Exception: pass
        print(json.dumps({"status":"failed","error":str(exc)},ensure_ascii=False),file=sys.stderr);return 2
    if args.command not in {"run-step","run-image-asset","run-video-shot"}: print(json.dumps(result,ensure_ascii=False,sort_keys=True))
    return 0


if __name__=="__main__": raise SystemExit(main())
