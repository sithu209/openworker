import pytest

from coworker.engineering.contracts import HealthReport, HealthStatus
from coworker.engineering.e2e_verify import run_rc_column_e2e


COLUMN={"component_id":"C1","width_mm":600,"depth_mm":600,"clear_height_mm":3500,
        "concrete_grade":"C35","steel_grade":"HRB400","axial_force_kn":1800,"moment_x_knm":220}


def _artifact(aid,kind):
    return {"id":aid,"project_id":"prj1","job_id":"job1","component_id":"C1","kind":kind,
            "uri":f"/tmp/{aid}","media_type":"application/octet-stream","checksum":"a"*64,"revision":1}


class FakeClient:
    def __init__(self, ready=True):
        self.ready=ready; self.reviews=[]; self.publishes=[]; self.status="draft"
        self.artifacts=(_artifact("calc","calculation_trace"),_artifact("draw","drawing_svg"),_artifact("bim","ifc_model"))
    def readiness(self): return HealthReport(status=HealthStatus.READY if self.ready else HealthStatus.UNAVAILABLE)
    def get_project(self,project_id): return {"id":project_id}
    def create_job(self,**kwargs): self.status="draft"; return {"id":"job1","project_id":kwargs["project_id"],"status":"draft","revision":1}
    def execute_rc_column_flow(self,*,job_id,column):
        self.status="review"
        return {"job":{"id":job_id,"project_id":"prj1","status":"review","revision":4},
                "tasks":[{"code":"rc-column-calculation"},{"code":"rc-column-drawing"},{"code":"rc-column-bim"}],
                "stages":[{"engine":"design-forge"},{"engine":"engsketch"},{"engine":"aibim"}],
                "artifacts":list(self.artifacts)}
    def submit_artifact_review(self,**kwargs): self.reviews.append(kwargs); return {"id":"r"+kwargs["artifact_id"],**kwargs}
    def approval_status(self,job_id):
        approved=len(self.reviews)==len(self.artifacts)
        if approved: self.status="completed"
        return {"job_id":job_id,"approved":approved}
    def get_job(self,job_id): return {"id":job_id,"project_id":"prj1","status":self.status,"revision":5}
    def publish_job(self,**kwargs):
        self.publishes.append(kwargs); self.status="published"
        return {"delivery":{"id":"del1","job_id":kwargs["job_id"],"status":"published"},"website":{"status":"ready"}}


def test_e2e_default_stops_at_review_without_implicit_governance():
    client=FakeClient()
    result=run_rc_column_e2e(client,project_id="prj1",job_code="E2E-1",column=COLUMN)
    assert result.job["status"]=="review"
    assert result.approval_status is None and result.delivery is None
    assert client.reviews==[] and client.publishes==[]
    assert len(result.artifacts)==3


def test_e2e_can_explicitly_review_and_publish_full_current_artifact_set():
    client=FakeClient()
    result=run_rc_column_e2e(client,project_id="prj1",job_code="E2E-2",column=COLUMN,
                             reviewer="engineer-a",publisher="publisher-a")
    assert len(client.reviews)==3
    assert result.approval_status["approved"] is True
    assert result.delivery["status"]=="published"
    assert result.job["status"]=="published"


def test_e2e_publish_cannot_bypass_review_and_unready_fails_before_create():
    with pytest.raises(ValueError,match="requires reviewer"):
        run_rc_column_e2e(FakeClient(),project_id="prj1",job_code="E2E-3",column=COLUMN,publisher="p")
    client=FakeClient(ready=False)
    with pytest.raises(RuntimeError,match="not ready"):
        run_rc_column_e2e(client,project_id="prj1",job_code="E2E-4",column=COLUMN)
