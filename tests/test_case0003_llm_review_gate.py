from __future__ import annotations

from pathlib import Path


def test_case0003_workflow_cannot_bypass_llm_review_gate():
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github" / "workflows" / "case-0003-yujing-bridge-ul7.yml").read_text(encoding="utf-8")
    assert "case0003_review_handoff.py" in workflow
    assert "WAITING_LLM_REVIEW" in workflow
    assert "accepted pointer moved before LLM review" in workflow
    assert "case0003_final_acceptance.py --workspace" not in workflow
    assert "WorkLedger terminal delivery evidence" not in workflow


def test_case0003_handoff_marks_llm_semantic_review_required_before_acceptance():
    root = Path(__file__).resolve().parents[1]
    handoff = (root / "scripts" / "case0003_review_handoff.py").read_text(encoding="utf-8")
    assert 'name="LLM Semantic Review"' in handoff
    assert 'status="pending"' in handoff
    assert 'required=True' in handoff
    assert 'status="WAITING_LLM_REVIEW"' in handoff
    assert "accept_revision(" not in handoff
    assert "deliver_revision(" not in handoff


def test_case0003_receipt_is_only_path_to_accept_and_delivery():
    root = Path(__file__).resolve().parents[1]
    apply_script = (root / "scripts" / "case0003_apply_llm_review.py").read_text(encoding="utf-8")
    assert "apply_review_finding(" in apply_script
    assert 'if result["verdict"] == "PASS"' in apply_script
    assert "accept_revision(revision_id)" in apply_script
    assert "deliver_revision(" in apply_script
    assert "TOOL_GAP_REWORK_REQUIRED" in apply_script
    assert "TUNING_REQUIRED" in apply_script
