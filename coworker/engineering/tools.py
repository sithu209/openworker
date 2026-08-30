"""OpenWorker tool facade for the AI-Engineering-OS control plane.

Read operations are low-risk. Mutations of authoritative engineering state always use
OpenWorker's standard approval gate; AI-Engineering-OS remains the domain authority.
"""
from __future__ import annotations

import json
from typing import Any

import aisuite as ai

from .engineering_os import EngineeringOSClient
from .flow_client import EngineeringOSFlowClient


def _set_tool_contract(func: Any, *, schema: dict[str, Any], risk_level: str,
                       capabilities: list[str], requires_approval: bool) -> Any:
    func.__coworker_schema__ = schema
    func.__aisuite_tool_metadata__ = ai.ToolMetadata(
        name=func.__name__, category="engineering", risk_level=risk_level,
        capabilities=capabilities, requires_approval=requires_approval,
        description=schema["function"]["description"],
    )
    return func


def _schema(name: str, description: str, properties: dict[str, Any],
            required: list[str] | None = None) -> dict[str, Any]:
    return {"type":"function","function":{"name":name,"description":description,
        "parameters":{"type":"object","properties":properties,"required":required or [],
                      "additionalProperties":False}}}


def engineering_os_tools(client: EngineeringOSClient | None = None) -> list[Any]:
    api = client or EngineeringOSFlowClient()

    def engineering_system_readiness() -> dict[str, Any]:
        health, readiness = api.health(), api.readiness()
        result={"health":health.to_dict(),"readiness":readiness.to_dict(),
                "ready":health.ready and readiness.ready}
        if result["ready"]:
            result["schema_version"]=api.schema_version()
            result["capabilities"]=sorted(cap.value for cap in api.capabilities())
        else:
            result["schema_version"]=None; result["capabilities"]=[]
        return result
    _set_tool_contract(engineering_system_readiness,
        schema=_schema("engineering_system_readiness","Check AI-Engineering-OS health, readiness, schema version, and configured engineering capabilities.",{}),
        risk_level="low",capabilities=["read","engineering"],requires_approval=False)

    def engineering_list_projects() -> dict[str, Any]:
        items=api.list_projects(); return {"items":items,"count":len(items)}
    _set_tool_contract(engineering_list_projects,
        schema=_schema("engineering_list_projects","List Projects registered in authoritative AI-Engineering-OS.",{}),
        risk_level="low",capabilities=["read","engineering","project"],requires_approval=False)

    def engineering_get_project(project_id: str) -> dict[str, Any]: return api.get_project(project_id)
    _set_tool_contract(engineering_get_project,
        schema=_schema("engineering_get_project","Get one AI-Engineering-OS Project by stable project_id.",
            {"project_id":{"type":"string","description":"Stable Project ID."}},["project_id"]),
        risk_level="low",capabilities=["read","engineering","project"],requires_approval=False)

    def engineering_list_jobs(project_id: str = "") -> dict[str, Any]:
        items=api.list_jobs(project_id=project_id.strip() or None)
        return {"items":items,"count":len(items),"project_id":project_id.strip() or None}
    _set_tool_contract(engineering_list_jobs,
        schema=_schema("engineering_list_jobs","List AI-Engineering-OS Jobs, optionally filtered by project_id.",
            {"project_id":{"type":"string","description":"Optional stable Project ID."}}),
        risk_level="low",capabilities=["read","engineering","job"],requires_approval=False)

    def engineering_get_job(job_id: str) -> dict[str, Any]: return api.get_job(job_id)
    _set_tool_contract(engineering_get_job,
        schema=_schema("engineering_get_job","Get one AI-Engineering-OS Job including status, revision and delivery paths.",
            {"job_id":{"type":"string","description":"Stable Job ID."}},["job_id"]),
        risk_level="low",capabilities=["read","engineering","job"],requires_approval=False)

    def engineering_create_job(project_id: str, code: str, name: str, user_request: str,
                               expected_deliverables: list[str] | None = None,
                               priority: str = "normal", metadata_json: str = "") -> dict[str, Any]:
        metadata=None
        if metadata_json.strip():
            try: decoded=json.loads(metadata_json)
            except json.JSONDecodeError as exc: raise ValueError("metadata_json must be valid JSON") from exc
            if not isinstance(decoded,dict): raise ValueError("metadata_json must encode a JSON object")
            metadata=decoded
        return api.create_job(project_id=project_id,code=code,name=name,user_request=user_request,
            expected_deliverables=expected_deliverables,priority=priority,metadata=metadata)
    _set_tool_contract(engineering_create_job,
        schema=_schema("engineering_create_job","Create a new AI-Engineering-OS Job. This mutates authoritative engineering state and requires approval.",{
            "project_id":{"type":"string"},"code":{"type":"string"},"name":{"type":"string"},
            "user_request":{"type":"string"},"expected_deliverables":{"type":"array","items":{"type":"string"}},
            "priority":{"type":"string","enum":["low","normal","high","urgent"]},
            "metadata_json":{"type":"string"}},["project_id","code","name","user_request"]),
        risk_level="medium",capabilities=["write","engineering","job"],requires_approval=True)

    def engineering_execute_rc_column_flow(job_id: str, column: dict[str, Any]) -> dict[str, Any]:
        executor = getattr(api, "execute_rc_column_flow", None)
        if not callable(executor):
            raise RuntimeError("configured AI-Engineering-OS client does not expose rc-column managed flow")
        return executor(job_id=job_id, column=column)
    _set_tool_contract(engineering_execute_rc_column_flow,
        schema=_schema("engineering_execute_rc_column_flow","Execute the existing AI-Engineering-OS RC-column managed flow for an already-created canonical Job. This mutates authoritative Job/Artifact state and requires approval.",{
            "job_id":{"type":"string"},
            "column":{"type":"object","additionalProperties":True}},["job_id","column"]),
        risk_level="medium",capabilities=["write","engineering","job","flow"],requires_approval=True)

    def engineering_get_approval_status(job_id: str) -> dict[str, Any]:
        return api.approval_status(job_id)
    _set_tool_contract(engineering_get_approval_status,
        schema=_schema("engineering_get_approval_status","Read AI-Engineering-OS derived approval status for all current Artifact revisions in a Job.",
            {"job_id":{"type":"string"}},["job_id"]),
        risk_level="low",capabilities=["read","engineering","review"],requires_approval=False)

    def engineering_list_job_reviews(job_id: str) -> dict[str, Any]:
        items=api.list_job_reviews(job_id); return {"items":items,"count":len(items)}
    _set_tool_contract(engineering_list_job_reviews,
        schema=_schema("engineering_list_job_reviews","List authoritative Artifact review records for a Job.",
            {"job_id":{"type":"string"}},["job_id"]),
        risk_level="low",capabilities=["read","engineering","review"],requires_approval=False)

    def engineering_submit_artifact_review(job_id: str, artifact_id: str, reviewer: str,
                                           decision: str, comment: str = "") -> dict[str, Any]:
        return api.submit_artifact_review(job_id=job_id,artifact_id=artifact_id,reviewer=reviewer,
                                          decision=decision,comment=comment)
    _set_tool_contract(engineering_submit_artifact_review,
        schema=_schema("engineering_submit_artifact_review","Submit an authoritative Artifact review. Approved/rejected/rework decisions can change Job lifecycle and require user approval.",{
            "job_id":{"type":"string"},"artifact_id":{"type":"string"},"reviewer":{"type":"string"},
            "decision":{"type":"string","enum":["approved","rejected","rework"]},
            "comment":{"type":"string"}},["job_id","artifact_id","reviewer","decision"]),
        risk_level="medium",capabilities=["write","engineering","review"],requires_approval=True)

    def engineering_list_deliveries(job_id: str) -> dict[str, Any]:
        items=api.list_deliveries(job_id); return {"items":items,"count":len(items)}
    _set_tool_contract(engineering_list_deliveries,
        schema=_schema("engineering_list_deliveries","List published Delivery revisions for a Job.",
            {"job_id":{"type":"string"}},["job_id"]),
        risk_level="low",capabilities=["read","engineering","delivery"],requires_approval=False)

    def engineering_publish_job(job_id: str, publisher: str, note: str = "") -> dict[str, Any]:
        return api.publish_job(job_id=job_id,publisher=publisher,note=note)
    _set_tool_contract(engineering_publish_job,
        schema=_schema("engineering_publish_job","Publish an approved completed Job through AI-Engineering-OS. OS rechecks approvals and Artifact checksums; this external side effect requires approval.",{
            "job_id":{"type":"string"},"publisher":{"type":"string"},"note":{"type":"string"}},
            ["job_id","publisher"]),
        risk_level="medium",capabilities=["write","engineering","delivery"],requires_approval=True)

    return [engineering_system_readiness,engineering_list_projects,engineering_get_project,
            engineering_list_jobs,engineering_get_job,engineering_create_job,
            engineering_execute_rc_column_flow,engineering_get_approval_status,
            engineering_list_job_reviews,engineering_submit_artifact_review,
            engineering_list_deliveries,engineering_publish_job]
