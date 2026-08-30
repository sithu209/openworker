"""Case 0005 deterministic local lifecycle mapping.

The lifecycle stage never accepts model-invented project/job/revision/path identities.
Every claim is derived from already accepted Case evidence and bounded workspace paths.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping

from .case_worklist import CaseWorklistError


class Case0005LifecycleMixin:
    def _step_evidence(self, worklist, step_id: str) -> Mapping[str, Any]:
        value = worklist.step(step_id).evidence
        if not isinstance(value, Mapping):
            raise CaseWorklistError(f"step {step_id} evidence is unavailable")
        return value

    def _required_evidence(self, worklist, step_id: str, key: str) -> Any:
        value = self._step_evidence(worklist, step_id).get(key)
        if value is None or value == "" or value == []:
            raise CaseWorklistError(f"step {step_id} missing required durable evidence {key}")
        return value

    def _workspace_relpath(self, raw: Any, label: str) -> str:
        text = str(raw or "").strip()
        if not text:
            raise CaseWorklistError(f"{label} is empty")
        path = Path(text)
        if not path.is_absolute():
            rel = path
        else:
            try:
                rel = path.resolve().relative_to(self.workspace)
            except ValueError as exc:
                raise CaseWorklistError(f"{label} escapes Case workspace: {path}") from exc
        normalized = rel.as_posix()
        if normalized in {".", ".."} or normalized.startswith("../"):
            raise CaseWorklistError(f"{label} escapes Case workspace")
        return normalized

    def _write_request(self, relpath: str, payload: Mapping[str, Any]) -> str:
        clean = Path(relpath.replace("/", os.sep))
        if clean.is_absolute() or clean.as_posix() in {".", ".."} or clean.as_posix().startswith("../"):
            raise CaseWorklistError(f"request relpath is not bounded: {relpath}")
        path = (self.workspace / clean).resolve()
        try:
            path.relative_to(self.workspace)
        except ValueError as exc:
            raise CaseWorklistError(f"request path escapes Case workspace: {path}") from exc
        self._write_json_atomic(path, dict(payload))
        return relpath

    def _claim_inputs(self, worklist, step, action: str, spec):
        common = {"workspace_root": str(self.workspace), "assigned_host": worklist.assigned_host}

        if action == "openworker.review.await-drive" and step.step_id in {"0005-027", "0005-057", "0005-100"}:
            return {
                **common,
                "step_id": step.step_id,
                "evidence_relpath": f"evidence/{step.step_id}-drive-gate.json",
                "timeout_seconds": 43200,
            }

        if action == "openworker.workledger.revision" and step.step_id == "0005-080":
            final_sha = str(self._required_evidence(worklist, "0005-070", "final_mp4_sha256"))
            if len(final_sha.strip()) != 64:
                raise CaseWorklistError("0005-070 final_mp4_sha256 is invalid")
            return {
                **common,
                "final_mp4_relpath": "final/final.mp4",
                "evidence_relpath": "evidence/case0005-workledger-revision.json",
            }

        if action == "engineering_os.case0005.identity" and step.step_id == "0005-082":
            return {
                **common,
                "evidence_relpath": ".openworker/engineering-os-identity.json",
            }

        if action == "engineering_os.artifact.register" and step.step_id == "0005-085":
            project_id = str(self._required_evidence(worklist, "0005-082", "project_id"))
            job_id = str(self._required_evidence(worklist, "0005-082", "job_id"))
            final_sha = str(self._required_evidence(worklist, "0005-080", "final_mp4_sha256")).lower()
            request_rel = ".openworker/requests/0005-085-engineering-os-artifact-register.json"
            evidence_rel = "evidence/0005-085-engineering-os-artifact-register.json"
            self._write_request(request_rel, {
                "schema_version": "openworker-case0005-engineering-os-artifact-register/v1",
                "case_id": worklist.case_id,
                "project_id": project_id,
                "job_id": job_id,
                "artifacts": [{
                    "path": str((self.workspace / "final" / "final.mp4").resolve()),
                    "kind": "video/final",
                    "media_type": "video/mp4",
                    "sha256": final_sha,
                    "source_run_id": "local-supervisor",
                }],
            })
            return {**common, "request_relpath": request_rel, "evidence_relpath": evidence_rel}

        if action == "openworker.case.publish-artifacts" and step.step_id == "0005-090":
            revision_id = str(self._required_evidence(worklist, "0005-080", "revision_id"))
            manifest = self._workspace_relpath(
                self._required_evidence(worklist, "0005-080", "manifest"),
                "WorkLedger revision manifest",
            )
            publish_revision = f"case0005-final-review-{revision_id}"
            return {
                **common,
                "case_id": worklist.case_id,
                "step_id": step.step_id,
                "revision_id": publish_revision,
                "work_code": "CASE0005-FINAL-REVIEW",
                "artifacts": ["final/final.mp4", manifest],
                "run_id": publish_revision,
            }

        if action == "engineering_os.delivery.publish" and step.step_id == "0005-110":
            job_id = str(self._required_evidence(worklist, "0005-082", "job_id"))
            accepted_revision_id = str(self._required_evidence(worklist, "0005-100", "accepted_revision_id"))
            request_rel = ".openworker/requests/0005-110-engineering-os-delivery-publish.json"
            evidence_rel = "evidence/0005-110-engineering-os-delivery-publish.json"
            self._write_request(request_rel, {
                "schema_version": "openworker-case0005-engineering-os-delivery-publish/v1",
                "case_id": worklist.case_id,
                "job_id": job_id,
                "publisher": "openworker-local-supervisor",
                "note": f"ChatGPT accepted WorkLedger revision {accepted_revision_id}",
                "accepted_revision_id": accepted_revision_id,
            })
            return {**common, "job_id": job_id, "request_relpath": request_rel, "evidence_relpath": evidence_rel}

        if action == "openworker.delivery.validate" and step.step_id == "0005-120":
            job_id = str(self._required_evidence(worklist, "0005-082", "job_id"))
            delivery_id = str(self._required_evidence(worklist, "0005-110", "delivery_id"))
            delivery_revision = self._required_evidence(worklist, "0005-110", "delivery_revision")
            review_receipt = self._workspace_relpath(
                self._required_evidence(worklist, "0005-100", "review_receipt"),
                "ChatGPT review receipt",
            )
            request_rel = ".openworker/requests/0005-120-delivery-validate.json"
            evidence_rel = "evidence/0005-120-delivery-validate.json"
            self._write_request(request_rel, {
                "schema_version": "openworker-case0005-delivery-validation-request/v1",
                "case_id": worklist.case_id,
                "job_id": job_id,
                "delivery_id": delivery_id,
                "delivery_revision": delivery_revision,
                "required_kinds": ["video/final"],
                "required_paths": [],
                "review_receipt": str((self.workspace / review_receipt.replace("/", os.sep)).resolve()),
                "expected_accepted_revision_id": str(self._required_evidence(worklist, "0005-100", "accepted_revision_id")),
            })
            return {**common, "request_relpath": request_rel, "evidence_relpath": evidence_rel}

        return super()._claim_inputs(worklist, step, action, spec)

    def _acceptance_evidence(self, step, local_result: Mapping[str, Any]) -> dict[str, Any]:
        action = str(local_result.get("capability_id", "")).strip()
        evidence = local_result.get("evidence")
        if not isinstance(evidence, Mapping):
            return super()._acceptance_evidence(step, local_result)

        if action == "openworker.review.await-drive":
            if bool(evidence.get("github_action_used_for_business_execution")) or bool(evidence.get("cloud_command_ingress_used")):
                raise CaseWorklistError("Drive review gate must not use GitHub business execution or cloud command ingress")
            if step.step_id == "0005-027":
                mapped = {
                    "approved_storyboard_pptx_sha256": evidence.get("approved_storyboard_pptx_sha256"),
                    "approval_decision": evidence.get("approval_decision"),
                    "approval_receipt": evidence.get("approval_receipt"),
                }
            elif step.step_id == "0005-057":
                mapped = {
                    "approved_illustrated_storyboard_sha256": evidence.get("approved_illustrated_storyboard_sha256"),
                    "approval_decision": evidence.get("approval_decision"),
                    "approval_receipt": evidence.get("approval_receipt"),
                }
            elif step.step_id == "0005-100":
                mapped = {
                    "review_receipt": evidence.get("review_receipt"),
                    "review_decision": evidence.get("review_decision"),
                    "accepted_revision_id": evidence.get("accepted_revision_id"),
                }
            else:
                raise CaseWorklistError(f"Drive review gate acceptance is not mapped for {step.step_id}")
            return self._require_keys(mapped, step.acceptance)

        if action == "openworker.workledger.revision":
            return self._require_keys({
                "artifact_ids": evidence.get("artifact_ids"),
                "revision_id": evidence.get("revision_id"),
                "manifest_sha256": evidence.get("manifest_sha256"),
                "final_mp4_sha256": evidence.get("final_mp4_sha256"),
            }, step.acceptance)

        if action == "engineering_os.case0005.identity":
            return self._require_keys({
                "project_id": evidence.get("project_id"),
                "job_id": evidence.get("job_id"),
                "identity_receipt": evidence.get("identity_receipt"),
            }, step.acceptance)

        if action == "engineering_os.artifact.register":
            receipt = evidence.get("receipt") if isinstance(evidence.get("receipt"), Mapping) else {}
            return self._require_keys({
                "artifact_ids": evidence.get("artifact_ids"),
                "engineering_os_receipt": evidence.get("receipt_path"),
                "project_id": receipt.get("project_id"),
                "job_id": receipt.get("job_id"),
            }, step.acceptance)

        if action == "engineering_os.delivery.publish":
            receipt = evidence.get("receipt") if isinstance(evidence.get("receipt"), Mapping) else {}
            return self._require_keys({
                "delivery_id": receipt.get("delivery_id"),
                "delivery_revision": receipt.get("delivery_revision"),
                "accepted_revision_id": self.runtime.load().step("0005-100").evidence.get("accepted_revision_id"),
            }, step.acceptance)

        if action == "openworker.delivery.validate":
            receipt = evidence.get("receipt") if isinstance(evidence.get("receipt"), Mapping) else {}
            verified = receipt.get("verified_items") if isinstance(receipt.get("verified_items"), list) else []
            final_item = next((item for item in verified if isinstance(item, Mapping) and str(item.get("kind", "")) == "video/final"), None)
            return self._require_keys({
                "package_path": evidence.get("package_path"),
                "final_mp4": final_item.get("path") if isinstance(final_item, Mapping) else None,
                "final_validation": evidence.get("final_validation"),
                "review_provenance": receipt.get("review_provenance") or receipt.get("review_receipt"),
            }, step.acceptance)

        return super()._acceptance_evidence(step, local_result)
