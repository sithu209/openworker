from __future__ import annotations

import pytest

from coworker.engineering.runtime_ab import RuntimeABError, compare_runtime_cases, run_runtime_case
from coworker.events import Event, EventType


class FakeRuntime:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.sources = []

    async def run(self, user_input, *, source=None, display=None):
        self.sources.append(source)
        yield Event(EventType.TURN_START, {"runtime": "fake"})
        if self.fail:
            yield Event(EventType.ERROR, {"error": "boom"})
            yield Event(EventType.TURN_END, {"stop_reason": "error"})
            return
        yield Event(EventType.ASSISTANT_MESSAGE, {"content": "done"})
        yield Event(EventType.TURN_END, {"stop_reason": "end_turn"})


class FakeObserver:
    def __init__(self, *, variant: str = "same") -> None:
        self.variant = variant

    def get_job(self, job_id: str):
        project = "project-native" if job_id == "job-native" else "project-harness"
        return {"id": job_id, "project_id": project, "status": "review"}

    def list_job_artifacts(self, job_id: str):
        suffix = "A" if self.variant == "different" and job_id == "job-harness" else "X"
        return [
            {
                "id": f"a-{job_id}-1",
                "kind": "calculation_trace",
                "component_id": "C1",
                "media_type": "application/json",
                "checksum": f"calc-{suffix}",
            },
            {
                "id": f"a-{job_id}-2",
                "kind": "drawing_svg",
                "component_id": "C1",
                "media_type": "image/svg+xml",
                "checksum": f"draw-{suffix}",
            },
            {
                "id": f"a-{job_id}-3",
                "kind": "bim_ifc",
                "component_id": "C1",
                "media_type": "application/x-step",
                "checksum": f"ifc-{suffix}",
            },
        ]


@pytest.mark.asyncio
async def test_runtime_case_requires_real_runtime_event_contract_and_os_evidence() -> None:
    runtime = FakeRuntime()
    observer = FakeObserver()
    result = await run_runtime_case(
        runtime,
        observer,
        runtime_name="native",
        project_id="project-native",
        job_id="job-native",
        prompt="execute RC golden path",
    )
    assert result.job_status == "review"
    assert {item.family for item in result.fingerprints} == {"calculation", "drawing", "bim"}
    assert runtime.sources == [
        {
            "project_id": "project-native",
            "engineering_job_id": "job-native",
            "verification": "openworker-h8-rc-runtime-ab",
        }
    ]


@pytest.mark.asyncio
async def test_runtime_case_rejects_runtime_error_even_if_os_has_artifacts() -> None:
    with pytest.raises(RuntimeABError, match="emitted ERROR"):
        await run_runtime_case(
            FakeRuntime(fail=True),
            FakeObserver(),
            runtime_name="harness",
            project_id="project-harness",
            job_id="job-harness",
            prompt="execute RC golden path",
        )


@pytest.mark.asyncio
async def test_non_strict_equivalence_ignores_random_ids_and_checksums() -> None:
    observer = FakeObserver(variant="different")
    native = await run_runtime_case(
        FakeRuntime(), observer,
        runtime_name="native", project_id="project-native", job_id="job-native",
        prompt="same prompt", strict_checksums=False,
    )
    harness = await run_runtime_case(
        FakeRuntime(), observer,
        runtime_name="harness", project_id="project-harness", job_id="job-harness",
        prompt="same prompt", strict_checksums=False,
    )
    report = compare_runtime_cases(native, harness, strict_checksums=False)
    assert report.artifact_family_counts_equal is True
    assert report.artifact_fingerprints_equal is True


@pytest.mark.asyncio
async def test_strict_equivalence_detects_engineering_output_checksum_drift() -> None:
    observer = FakeObserver(variant="different")
    native = await run_runtime_case(
        FakeRuntime(), observer,
        runtime_name="native", project_id="project-native", job_id="job-native",
        prompt="same prompt", strict_checksums=True,
    )
    harness = await run_runtime_case(
        FakeRuntime(), observer,
        runtime_name="harness", project_id="project-harness", job_id="job-harness",
        prompt="same prompt", strict_checksums=True,
    )
    report = compare_runtime_cases(native, harness, strict_checksums=True)
    assert report.artifact_family_counts_equal is True
    assert report.artifact_fingerprints_equal is False


@pytest.mark.asyncio
async def test_missing_ifc_fails_instead_of_claiming_golden_job_success() -> None:
    class MissingIfc(FakeObserver):
        def list_job_artifacts(self, job_id: str):
            return super().list_job_artifacts(job_id)[:2]

    with pytest.raises(RuntimeABError, match="missing authoritative artifact families: bim"):
        await run_runtime_case(
            FakeRuntime(), MissingIfc(), runtime_name="harness",
            project_id="project-harness", job_id="job-harness",
            prompt="same prompt",
        )
