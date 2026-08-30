import json
import pytest

from coworker.engineering.engineering_os import EngineeringOSConfig, EngineeringOSContractError, TransportResponse
from coworker.engineering.flow_client import EngineeringOSFlowClient


class FakeTransport:
    def __init__(self, payload): self.payload=payload; self.calls=[]
    def request(self, method, url, *, body, headers, timeout):
        self.calls.append((method, url, json.loads(body or b"{}")))
        return TransportResponse(200, json.dumps(self.payload).encode())


def test_public_rc_flow_method_owns_route_and_payload():
    payload={"job":{},"tasks":[],"stages":[],"artifacts":[]}
    transport=FakeTransport(payload)
    client=EngineeringOSFlowClient(EngineeringOSConfig(),transport=transport)
    result=client.execute_rc_column_flow(job_id="job1",column={"component_id":"C1"})
    assert result is payload or result==payload
    method,url,body=transport.calls[0]
    assert method=="POST"
    assert url.endswith("/api/v1/jobs/job1/flows/rc-column")
    assert body=={"component_id":"C1"}


def test_public_rc_flow_rejects_bad_id_and_missing_contract():
    client=EngineeringOSFlowClient(transport=FakeTransport({"job":{},"tasks":[],"stages":[]}))
    with pytest.raises(ValueError):
        client.execute_rc_column_flow(job_id="bad/id",column={})
    with pytest.raises(EngineeringOSContractError,match="artifacts"):
        client.execute_rc_column_flow(job_id="job1",column={})
