"""H8 NativeRuntime vs DeepSeek Harness RC Golden Job A/B verifier.

The verifier deliberately drives the AgentRuntime contract on both sides.  It
then reads authoritative Engineering-OS Job/Artifact state and compares stable
engineering evidence rather than runtime-private transcript details or random
artifact ids.
"""
from __future__ import annotations

import time
from collections import Counter
from dataclasses import dataclass
from typing import Any, AsyncIterator, Mapping, Protocol, Sequence

from ..events import Event, EventType


class RuntimeABError(RuntimeError):
    pass


class RuntimeDriver(Protocol):
    def run(
        self,
        user_input: str | list,
        *,
        source: dict[str, Any] | None = None,
        display: str | None = None,
    ) -> AsyncIterator[Event]: ...


class EngineeringObservationClient(Protocol):
    def get_job(self, job_id: str) -> dict[str, Any]: ...
    def list_job_artifacts(self, job_id: str) -> Sequence[dict[str, Any]]: ...


_REQUIRED_ARTIFACT_FAMILIES = ("calculation", "drawing", "bim")
_ACCEPTABLE_TERMINAL_JOB_STATES = frozenset({"review", "completed", "published"})


@dataclass(frozen=True, order=True)
class ArtifactFingerprint:
    family: str
    kind: str
    component_id: str
    media_type: str
    checksum: str | None


@dataclass(frozen=True)
class RuntimeCaseResult:
    runtime: str
    project_id: str
    job_id: str
    elapsed_seconds: float
    event_types: tuple[str, ...]
    stop_reason: str
    job_status: str
    artifacts: tuple[dict[str, Any], ...]
    fingerprints: tuple[ArtifactFingerprint, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "runtime": self.runtime,
            "project_id": self.project_id,
            "job_id": self.job_id,
            "elapsed_seconds": self.elapsed_seconds,
            "event_types": list(self.event_types),
            "stop_reason": self.stop_reason,
            "job_status": self.job_status,
            "artifact_fingerprints": [
                {
                    "family": item.family,
                    "kind": item.kind,
                    "component_id": item.component_id,
                    "media_type": item.media_type,
                    "checksum": item.checksum,
                }
                for item in self.fingerprints
            ],
        }


@dataclass(frozen=True)
class RuntimeABReport:
    native: RuntimeCaseResult
    harness: RuntimeCaseResult
    artifact_family_counts_equal: bool
    artifact_fingerprints_equal: bool
    strict_checksums: bool
    harness_to_native_time_ratio: float | None

    @property
    def equivalent(self) -> bool:
        return self.artifact_fingerprints_equal

    def to_dict(self) -> dict[str, Any]:
        return {
            "native": self.native.to_dict(),
            "harness": self.harness.to_dict(),
            "artifact_family_counts_equal": self.artifact_family_counts_equal,
            "artifact_fingerprints_equal": self.artifact_fingerprints_equal,
            "strict_checksums": self.strict_checksums,
            "harness_to_native_time_ratio": self.harness_to_native_time_ratio,
            "equivalent": self.equivalent,
        }


def _required_text(payload: Mapping[str, Any], key: str, context: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise RuntimeABError(f"{context} missing required field: {key}")
    return value.strip()


def _artifact_family(kind: str, media_type: str) -> str:
    token = f"{kind} {media_type}".lower()
    if any(word in token for word in ("calculation", "trace", "design", "calc")):
        return "calculation"
    if any(word in token for word in ("drawing", "svg", "png", "image")):
        return "drawing"
    if any(word in token for word in ("bim", "ifc")):
        return "bim"
    return "other"


def fingerprint_artifacts(
    artifacts: Sequence[Mapping[str, Any]],
    *,
    strict_checksums: bool,
) -> tuple[ArtifactFingerprint, ...]:
    out: list[ArtifactFingerprint] = []
    for artifact in artifacts:
        kind = _required_text(artifact, "kind", "Engineering-OS Artifact")
        media = str(artifact.get("media_type") or "").strip()
        component = str(artifact.get("component_id") or "").strip()
        checksum_raw = artifact.get("checksum")
        checksum = str(checksum_raw).strip() if checksum_raw not in (None, "") else None
        if strict_checksums and not checksum:
            raise RuntimeABError(f"strict A/B requires checksum for artifact kind {kind}")
        out.append(
            ArtifactFingerprint(
                family=_artifact_family(kind, media),
                kind=kind.lower(),
                component_id=component,
                media_type=media.lower(),
                checksum=checksum if strict_checksums else None,
            )
        )
    return tuple(sorted(out))


def _assert_required_families(fingerprints: Sequence[ArtifactFingerprint], runtime: str) -> None:
    families = {item.family for item in fingerprints}
    missing = [name for name in _REQUIRED_ARTIFACT_FAMILIES if name not in families]
    if missing:
        raise RuntimeABError(
            f"{runtime} RC Golden Job missing authoritative artifact families: {', '.join(missing)}"
        )


async def run_runtime_case(
    runtime: RuntimeDriver,
    observer: EngineeringObservationClient,
    *,
    runtime_name: str,
    project_id: str,
    job_id: str,
    prompt: str,
    strict_checksums: bool = False,
) -> RuntimeCaseResult:
    runtime_name = runtime_name.strip()
    project_id = project_id.strip()
    job_id = job_id.strip()
    if not runtime_name or not project_id or not job_id or not prompt.strip():
        raise ValueError("runtime_name, project_id, job_id and prompt must not be empty")

    source = {
        "project_id": project_id,
        "engineering_job_id": job_id,
        "verification": "openworker-h8-rc-runtime-ab",
    }
    started = time.perf_counter()
    events = [event async for event in runtime.run(prompt, source=source)]
    elapsed = time.perf_counter() - started
    if not events:
        raise RuntimeABError(f"{runtime_name} emitted no runtime events")
    if any(event.type is EventType.ERROR for event in events):
        errors = [str(event.data.get("error", "")) for event in events if event.type is EventType.ERROR]
        raise RuntimeABError(f"{runtime_name} runtime emitted ERROR: {'; '.join(errors)}")
    if events[0].type is not EventType.TURN_START:
        raise RuntimeABError(f"{runtime_name} did not start with TURN_START")
    if events[-1].type is not EventType.TURN_END:
        raise RuntimeABError(f"{runtime_name} did not close with TURN_END")
    stop_reason = str(events[-1].data.get("stop_reason") or "").strip()
    if stop_reason in {"", "error", "cancelled"}:
        raise RuntimeABError(f"{runtime_name} ended with unacceptable stop_reason {stop_reason!r}")

    job = observer.get_job(job_id)
    if _required_text(job, "id", f"{runtime_name} Job") != job_id:
        raise RuntimeABError(f"{runtime_name} observer returned inconsistent job identity")
    if _required_text(job, "project_id", f"{runtime_name} Job") != project_id:
        raise RuntimeABError(f"{runtime_name} observer returned inconsistent project identity")
    job_status = _required_text(job, "status", f"{runtime_name} Job")
    if job_status not in _ACCEPTABLE_TERMINAL_JOB_STATES:
        raise RuntimeABError(
            f"{runtime_name} RC Golden Job did not reach review/completed/published; got {job_status}"
        )

    artifacts = tuple(observer.list_job_artifacts(job_id))
    if not artifacts:
        raise RuntimeABError(f"{runtime_name} RC Golden Job returned no artifacts")
    fingerprints = fingerprint_artifacts(artifacts, strict_checksums=strict_checksums)
    _assert_required_families(fingerprints, runtime_name)
    return RuntimeCaseResult(
        runtime=runtime_name,
        project_id=project_id,
        job_id=job_id,
        elapsed_seconds=elapsed,
        event_types=tuple(event.type.value for event in events),
        stop_reason=stop_reason,
        job_status=job_status,
        artifacts=artifacts,
        fingerprints=fingerprints,
    )


def compare_runtime_cases(
    native: RuntimeCaseResult,
    harness: RuntimeCaseResult,
    *,
    strict_checksums: bool,
) -> RuntimeABReport:
    native_family_counts = Counter(item.family for item in native.fingerprints)
    harness_family_counts = Counter(item.family for item in harness.fingerprints)
    family_equal = native_family_counts == harness_family_counts
    fingerprints_equal = native.fingerprints == harness.fingerprints
    ratio = None
    if native.elapsed_seconds > 0:
        ratio = harness.elapsed_seconds / native.elapsed_seconds
    return RuntimeABReport(
        native=native,
        harness=harness,
        artifact_family_counts_equal=family_equal,
        artifact_fingerprints_equal=fingerprints_equal,
        strict_checksums=strict_checksums,
        harness_to_native_time_ratio=ratio,
    )


async def run_rc_runtime_ab(
    *,
    native_runtime: RuntimeDriver,
    harness_runtime: RuntimeDriver,
    observer: EngineeringObservationClient,
    native_project_id: str,
    native_job_id: str,
    harness_project_id: str,
    harness_job_id: str,
    prompt: str,
    strict_checksums: bool = False,
) -> RuntimeABReport:
    native = await run_runtime_case(
        native_runtime,
        observer,
        runtime_name="native",
        project_id=native_project_id,
        job_id=native_job_id,
        prompt=prompt,
        strict_checksums=strict_checksums,
    )
    harness = await run_runtime_case(
        harness_runtime,
        observer,
        runtime_name="harness",
        project_id=harness_project_id,
        job_id=harness_job_id,
        prompt=prompt,
        strict_checksums=strict_checksums,
    )
    report = compare_runtime_cases(native, harness, strict_checksums=strict_checksums)
    if not report.equivalent:
        raise RuntimeABError(
            "Native/Harness RC Golden Job artifact fingerprints are not equivalent"
        )
    return report


__all__ = [
    "ArtifactFingerprint",
    "EngineeringObservationClient",
    "RuntimeABError",
    "RuntimeABReport",
    "RuntimeCaseResult",
    "RuntimeDriver",
    "compare_runtime_cases",
    "fingerprint_artifacts",
    "run_rc_runtime_ab",
    "run_runtime_case",
]
