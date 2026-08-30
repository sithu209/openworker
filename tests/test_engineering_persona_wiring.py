from pathlib import Path

from coworker.agents.base import AgentContext
from coworker.catalog import CATALOG, expand, risk_summary
from coworker.personas.manifest import load_manifest_file
from coworker.risk import RiskClass
from coworker.tools.todo import TodoList


def test_engineering_os_is_vetted_catalog_capability():
    capability = CATALOG["engineering_os"]
    assert capability.id == "engineering_os"
    assert RiskClass.READ in capability.risk
    assert RiskClass.EXTERNAL in capability.risk


def test_engineering_manifest_declares_control_plane_capability():
    path = Path(__file__).parents[1] / "coworker" / "personas" / "builtin" / "engineering.md"
    manifest = load_manifest_file(path, builtin=True)
    assert manifest.id == "engineering"
    assert "engineering_os" in manifest.tools


def test_catalog_expands_engineering_control_plane_and_governance_tools_without_special_engine_branching(tmp_path):
    context = AgentContext(workspace=tmp_path, todo=TodoList())
    tools = expand(["engineering_os"], context)
    names = [tool.__name__ for tool in tools]
    assert names == [
        "engineering_system_readiness",
        "engineering_list_projects",
        "engineering_get_project",
        "engineering_list_jobs",
        "engineering_get_job",
        "engineering_create_job",
        "engineering_execute_rc_column_flow",
        "engineering_get_approval_status",
        "engineering_list_job_reviews",
        "engineering_submit_artifact_review",
        "engineering_list_deliveries",
        "engineering_publish_job",
        "engineering_run_rc_column_flow",
        "engineering_generate_minimax_h3",
    ]


def test_persona_risk_summary_includes_external_side_effects():
    risks = risk_summary(["engineering_os"])
    assert risks == {RiskClass.READ, RiskClass.EXTERNAL}
