from __future__ import annotations
import httpx
from coworker.node_client import OpenWorkerNodeClient

def test_node_client_contract(monkeypatch):
    calls=[]
    def handler(request:httpx.Request)->httpx.Response:
        calls.append((request.method,request.url.path,request.url.query.decode()))
        if request.url.path=="/v1/node/status": return httpx.Response(200,json={"machine":"TESTHOST","online":True})
        if request.url.path=="/v1/jobs" and request.method=="POST": return httpx.Response(202,json={"job_id":"OWJ-1","accepted":True})
        if request.url.path.endswith("/retry"): return httpx.Response(202,json={"job_id":"OWJ-1","status":"queued_local"})
        if request.url.path=="/v1/queue/drain": return httpx.Response(200,json={"ok":True,"mode":request.url.params["mode"]})
        if request.url.path=="/v1/cluster/status": return httpx.Response(200,json={"online_count":3})
        if request.url.path=="/v1/cluster/agents": return httpx.Response(200,json={"count":12})
        if request.url.path=="/v1/cluster/route": return httpx.Response(200,json={"selected":{"node_id":"ul7"}})
        if request.url.path=="/v1/cluster/jobs" and request.method=="POST": return httpx.Response(202,json={"ack":{"job_id":"OWJ-C","accepted":True},"selected":{"node_id":"ul7"}})
        return httpx.Response(200,json={"job_id":"OWJ-1"})
    transport=httpx.MockTransport(handler);original=httpx.Client
    monkeypatch.setattr(httpx,"Client",lambda *a,**kw:original(transport=transport,base_url=kw.get("base_url","http://test"),timeout=kw.get("timeout",10)))
    c=OpenWorkerNodeClient("http://test")
    assert c.node_status()["online"] is True
    assert c.submit({"job_id":"OWJ-1"})["accepted"] is True
    assert c.retry("OWJ-1")["status"]=="queued_local"
    assert c.drain("all")["mode"]=="all"
    assert c.cluster_status()["online_count"]==3
    assert c.cluster_agents()["count"]==12
    assert c.cluster_route("any",["bridge"])["selected"]["node_id"]=="ul7"
    assert c.cluster_submit({"job_id":"OWJ-C"},["bridge"])["ack"]["accepted"] is True
    assert any(path=="/v1/jobs/OWJ-1/retry" for _,path,_ in calls)
