"""Tool surface for AI-Engineering-OS managed engineering flows."""
from __future__ import annotations

from typing import Any
import aisuite as ai

from .flow_client import EngineeringOSFlowClient
from .managed_rcflow import execute_managed_rc_column


def managed_engineering_tools(client: EngineeringOSFlowClient | None = None) -> list[Any]:
    api = client or EngineeringOSFlowClient()

    def engineering_run_rc_column_flow(
        job_id: str,
        component_id: str,
        width_mm: float,
        depth_mm: float,
        clear_height_mm: float,
        concrete_grade: str,
        steel_grade: str,
        axial_force_kn: float,
        moment_x_knm: float,
        cover_mm: float = 40,
        main_bar_diameter_mm: float = 25,
        main_bar_count: int = 8,
        tie_diameter_mm: float = 10,
        tie_spacing_mm: float = 150,
        ifc_schema: str = "IFC4",
    ) -> dict[str, Any]:
        result = execute_managed_rc_column(api, job_id=job_id, column=locals())
        return {
            "job": result.job,
            "tasks": list(result.tasks),
            "stages": list(result.stages),
            "artifacts": list(result.artifacts),
            "digital_thread": result.digital_thread,
        }

    engineering_run_rc_column_flow.__coworker_schema__ = {
        "type":"function","function":{"name":"engineering_run_rc_column_flow",
        "description":"Run the authoritative AI-Engineering-OS RC-column flow: structural calculation, engineering drawing, BIM/IFC, artifact registration, and transition to review.",
        "parameters":{"type":"object","additionalProperties":False,
        "properties":{
            "job_id":{"type":"string"},"component_id":{"type":"string"},
            "width_mm":{"type":"number"},"depth_mm":{"type":"number"},"clear_height_mm":{"type":"number"},
            "concrete_grade":{"type":"string"},"steel_grade":{"type":"string"},
            "axial_force_kn":{"type":"number"},"moment_x_knm":{"type":"number"},
            "cover_mm":{"type":"number"},"main_bar_diameter_mm":{"type":"number"},"main_bar_count":{"type":"integer"},
            "tie_diameter_mm":{"type":"number"},"tie_spacing_mm":{"type":"number"},"ifc_schema":{"type":"string"}},
        "required":["job_id","component_id","width_mm","depth_mm","clear_height_mm","concrete_grade","steel_grade","axial_force_kn","moment_x_knm"]}}}
    engineering_run_rc_column_flow.__aisuite_tool_metadata__ = ai.ToolMetadata(
        name="engineering_run_rc_column_flow", category="engineering", risk_level="high",
        capabilities=["write","engineering","structural","drawing","bim"],
        requires_approval=True,
        description="Execute the authoritative RC-column engineering flow in AI-Engineering-OS.",
    )
    return [engineering_run_rc_column_flow]
