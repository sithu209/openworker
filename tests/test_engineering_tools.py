from coworker.engineering import EngineeringCapability, HealthReport, HealthStatus
from coworker.engineering.tools import engineering_os_tools
from coworker.tools.registry import ToolRegistry


class FakeClient:
    def __init__(self):
        self.created = None
        self.executed_flow = None
        self.reviewed = None
        self.published = None

    def health(self): return HealthReport(status=HealthStatus.READY, details={"status":"ok"})
    def readiness(self): return HealthReport(status=HealthStatus.READY, details={"status":"ready"})
    def schema_version(self): return "1.0.0"
    def capabilities(self): return {EngineeringCapability.STRUCTURAL, EngineeringCapability.DRAWING}
    def list_projects(self): return [{"id":"project-1","code":"P001","name":"Demo"}]
    def get_project(self, project_id): return {"id":project_id,"code":"P001","name":"Demo"}
    def list_jobs(self, *, project_id=None): return [{"id":"job-1","project_id":project_id or "project-1","name":"RC Column"}]
    def get_job(self, job_id): return {"id":job_id,"status":"review"}
    def create_job(self, **kwargs): self.created=kwargs; return {"id":"job-created",**kwargs}
    def execute_rc_column_flow(self, **kwargs):
        self.executed_flow=kwargs
        return {"job":{"id":kwargs["job_id"]},"tasks":[],"stages":[],"artifacts":[]}
    def approval_status(self, job_id): return {"job_id":job_id,"approved":False,"total":1,"approved_count":0,"pending_artifact_ids":["art-1"],"latest_reviews":{}}
    def list_job_reviews(self, job_id): return [{"id":"rev-1","job_id":job_id,"artifact_id":"art-1","decision":"approved"}]
    def submit_artifact_review(self, **kwargs): self.reviewed=kwargs; return {"id":"rev-new",**kwargs}
    def list_deliveries(self, job_id): return [{"id":"del-1","job_id":job_id,"revision":1}]
    def publish_job(self, **kwargs): self.published=kwargs; return {"delivery":{"id":"del-new","job_id":kwargs["job_id"]},"website":{"status":"ready"}}


def _registry(client=None):
    registry=ToolRegistry(); registry.register_all(engineering_os_tools(client or FakeClient())); return registry


def test_facade_exposes_stable_tool_names():
    assert _registry().names() == [
        "engineering_system_readiness","engineering_list_projects","engineering_get_project",
        "engineering_list_jobs","engineering_get_job","engineering_create_job",
        "engineering_execute_rc_column_flow","engineering_get_approval_status",
        "engineering_list_job_reviews","engineering_submit_artifact_review",
        "engineering_list_deliveries","engineering_publish_job",
    ]


def test_readiness_returns_normalized_control_plane_summary():
    result=_registry().execute("engineering_system_readiness")
    assert result["ready"] is True
    assert result["schema_version"]=="1.0.0"
    assert result["capabilities"]==["drawing","structural"]


def test_read_tools_do_not_require_approval_but_mutations_do():
    registry=_registry()
    for name in ["engineering_system_readiness","engineering_list_projects","engineering_get_project",
                 "engineering_list_jobs","engineering_get_job","engineering_get_approval_status",
                 "engineering_list_job_reviews","engineering_list_deliveries"]:
        assert registry.get(name).metadata.requires_approval is False
    for name in ["engineering_create_job","engineering_execute_rc_column_flow",
                 "engineering_submit_artifact_review","engineering_publish_job"]:
        tool=registry.get(name)
        assert tool.metadata.requires_approval is True
        assert tool.metadata.category=="engineering"


def test_list_and_get_tools_delegate_without_reimplementing_domain_rules():
    registry=_registry()
    assert registry.execute("engineering_list_projects")["count"]==1
    assert registry.execute("engineering_get_project",{"project_id":"project-1"})["id"]=="project-1"
    assert registry.execute("engineering_list_jobs",{"project_id":"project-1"})["items"][0]["project_id"]=="project-1"
    assert registry.execute("engineering_get_job",{"job_id":"job-1"})["status"]=="review"
    assert registry.execute("engineering_get_approval_status",{"job_id":"job-1"})["approved"] is False
    assert registry.execute("engineering_list_job_reviews",{"job_id":"job-1"})["count"]==1
    assert registry.execute("engineering_list_deliveries",{"job_id":"job-1"})["count"]==1


def test_create_job_preserves_payload_and_decodes_metadata_json():
    client=FakeClient(); registry=_registry(client)
    result=registry.execute("engineering_create_job",{
        "project_id":"project-1","code":"JOB-001","name":"RC Column Design",
        "user_request":"Design one RC column","expected_deliverables":["calculation","drawing"],
        "priority":"high","metadata_json":'{"source":"openworker"}'})
    assert result["id"]=="job-created"
    assert client.created["metadata"]=={"source":"openworker"}


def test_rc_column_flow_uses_existing_client_and_requires_approval_metadata():
    client=FakeClient(); registry=_registry(client)
    payload={"component_id":"C1","width_mm":400}
    result=registry.execute("engineering_execute_rc_column_flow",{"job_id":"job-1","column":payload})
    assert result["job"]["id"]=="job-1"
    assert client.executed_flow=={"job_id":"job-1","column":payload}
    assert registry.get("engineering_execute_rc_column_flow").metadata.requires_approval is True


def test_governance_mutation_tools_delegate_exact_user_decision():
    client=FakeClient(); registry=_registry(client)
    review=registry.execute("engineering_submit_artifact_review",{
        "job_id":"job-1","artifact_id":"art-1","reviewer":"engineer-a",
        "decision":"rework","comment":"revise bars"})
    assert review["decision"]=="rework"
    assert client.reviewed=={"job_id":"job-1","artifact_id":"art-1","reviewer":"engineer-a","decision":"rework","comment":"revise bars"}
    published=registry.execute("engineering_publish_job",{"job_id":"job-1","publisher":"chief","note":"issued"})
    assert published["delivery"]["id"]=="del-new"
    assert client.published=={"job_id":"job-1","publisher":"chief","note":"issued"}


def test_create_job_rejects_non_object_metadata_before_remote_mutation():
    client=FakeClient(); registry=_registry(client)
    try:
        registry.execute("engineering_create_job",{"project_id":"project-1","code":"JOB-001",
            "name":"RC Column Design","user_request":"Design one RC column","metadata_json":"[]"})
    except ValueError as exc:
        assert "JSON object" in str(exc)
    else: raise AssertionError("non-object metadata_json must be rejected")
    assert client.created is None


def test_unready_control_plane_does_not_probe_modules():
    class UnreadyClient(FakeClient):
        def readiness(self): return HealthReport(status=HealthStatus.UNAVAILABLE, details={"status":"not_ready"})
        def schema_version(self): raise AssertionError("schema version must not be queried while unavailable")
        def capabilities(self): raise AssertionError("capabilities must not be queried while unavailable")
    result=_registry(UnreadyClient()).execute("engineering_system_readiness")
    assert result["ready"] is False
    assert result["schema_version"] is None
    assert result["capabilities"]==[]
