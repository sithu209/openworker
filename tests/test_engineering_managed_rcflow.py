import json
import pytest

from coworker.engineering.engineering_os import EngineeringOSConfig, EngineeringOSContractError, TransportResponse
from coworker.engineering.flow_client import EngineeringOSFlowClient
from coworker.engineering.managed_rcflow import execute_managed_rc_column


COLUMN = {
    "component_id":"C1","width_mm":600,"depth_mm":600,"clear_height_mm":3500,
    "concrete_grade":"C35","steel_grade":"HRB400","axial_force_kn":1800,"moment_x_knm":220,
}


class FakeTransport:
    def __init__(self, payload): self.payload=payload; self.calls=[]
    def request(self, method, url, *, body, headers, timeout):
        self.calls.append((method,url,json.loads(body or b"{}")))
        return TransportResponse(200, json.dumps(self.payload).encode())


def _artifact(aid, kind):
    return {"id":aid,"project_id":"prj1","job_id":"job1","component_id":"C1","kind":kind,
            "uri":f"/tmp/{aid}","media_type":"application/octet-stream","checksum":"a"*64,
            "revision":1}


def test_managed_flow_uses_authoritative_rcflow_route_and_requires_drawing_and_bim():
    payload={"job":{"id":"job1","project_id":"prj1","status":"review","revision":4},
             "tasks":[{"code":"rc-column-calculation"},{"code":"rc-column-drawing"},{"code":"rc-column-bim"}],
             "stages":[{"engine":"design-forge"},{"engine":"engsketch"},{"engine":"aibim"}],
             "artifacts":[_artifact("a1","calculation_trace"),_artifact("a2","drawing_svg"),_artifact("a3","ifc_model")]}
    transport=FakeTransport(payload)
    client=EngineeringOSFlowClient(EngineeringOSConfig(),transport=transport)
    result=execute_managed_rc_column(client,job_id="job1",column=COLUMN)
    assert transport.calls[0][0]=="POST"
    assert transport.calls[0][1].endswith("/api/v1/jobs/job1/flows/rc-column")
    assert result.job["status"]=="review"
    assert len(result.artifacts)==3
    assert len(result.digital_thread["evidence"])==4


def test_managed_flow_fails_closed_on_job_identity_mismatch():
    transport=FakeTransport({"job":{"id":"other","status":"review"},"tasks":[],"stages":[],"artifacts":[]})
    client=EngineeringOSFlowClient(transport=transport)
    with pytest.raises(EngineeringOSContractError,match="identity"):
        execute_managed_rc_column(client,job_id="job1",column=COLUMN)
    assert len(transport.calls)==1


def test_managed_flow_requires_drawing_and_bim_artifacts():
    payload={"job":{"id":"job1","project_id":"prj1","status":"review","revision":4},
             "tasks":[],"stages":[],"artifacts":[_artifact("a1","calculation_trace")]}
    client=EngineeringOSFlowClient(transport=FakeTransport(payload))
    with pytest.raises(EngineeringOSContractError,match="drawing"):
        execute_managed_rc_column(client,job_id="job1",column=COLUMN)


def test_managed_flow_rejects_missing_input_before_remote_call():
    transport=FakeTransport({})
    client=EngineeringOSFlowClient(transport=transport)
    broken=dict(COLUMN); broken.pop("steel_grade")
    with pytest.raises(ValueError,match="steel_grade"):
        execute_managed_rc_column(client,job_id="job1",column=broken)
    assert transport.calls==[]
