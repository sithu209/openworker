from coworker.engineering.managed_tools import managed_engineering_tools


class FakeClient:
    def __init__(self): self.calls=[]
    def execute_rc_column_flow(self, *, job_id, column):
        self.calls.append((job_id,column))
        artifact=lambda aid,kind:{"id":aid,"project_id":"p1","job_id":"j1","component_id":"C1","kind":kind,"uri":"/tmp/"+aid,"media_type":"x","checksum":"a"*64,"revision":1}
        return {"job":{"id":"j1","project_id":"p1","status":"review","revision":4},"tasks":[],"stages":[],"artifacts":[artifact("calc","calculation_trace"),artifact("draw","drawing_svg"),artifact("bim","ifc_model")]}


def test_managed_flow_tool_requires_approval_and_delegates_to_public_os_flow_api():
    client=FakeClient(); tool=managed_engineering_tools(client)[0]
    assert tool.__aisuite_tool_metadata__.requires_approval is True
    assert tool.__aisuite_tool_metadata__.risk_level == "high"
    result=tool("j1","C1",600,600,3500,"C35","HRB400",1800,220)
    assert client.calls[0][0]=="j1"
    assert client.calls[0][1]["component_id"]=="C1"
    assert result["job"]["status"]=="review"
    assert len(result["artifacts"])==3
