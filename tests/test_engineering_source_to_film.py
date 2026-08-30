import json

import pytest

from coworker.engineering.engineering_os import (
    EngineeringOSClient,
    EngineeringOSConfig,
    EngineeringOSContractError,
    TransportResponse,
)


class FakeTransport:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def request(self, method, url, *, body, headers, timeout):
        self.calls.append({
            "method": method,
            "url": url,
            "body": body,
            "headers": dict(headers),
            "timeout": timeout,
        })
        return self.response


def response(payload, status=200):
    return TransportResponse(status=status, body=json.dumps(payload).encode("utf-8"))


def make_client(payload, status=200):
    transport = FakeTransport(response(payload, status))
    return EngineeringOSClient(
        EngineeringOSConfig("http://127.0.0.1:8080", timeout_seconds=5),
        transport=transport,
    ), transport


def test_start_source_to_film_calls_only_os_domain_route_with_provenance_contract():
    client, transport = make_client({
        "schema_version": "engineering-os-source-to-film/1.0",
        "os_project_id": "prj_0002",
        "os_job_id": "job_0002",
        "studio_project_id": "os-job_0002",
        "studio_source_id": "source",
        "queue_id": "os-job_0002-production",
        "source": {"version": 1},
        "plan": {"version": 1},
        "queue": {"status": "running"},
        "artifact": {"id": "art_dispatch"},
    })

    result = client.start_source_to_film(
        job_id="job_0002",
        language="zh-Hant",
        target_duration_sec=20,
        default_shot_seconds=5,
        visual_style=["cinematic live action", "warm desert fantasy"],
        world_rules=["same Aladdin", "same brass lamp"],
        acceleration_profile="lightx2v-h3-4step",
        width=1280,
        height=720,
    )

    assert result["queue_id"] == "os-job_0002-production"
    assert len(transport.calls) == 1
    call = transport.calls[0]
    assert call["method"] == "POST"
    assert call["url"] == "http://127.0.0.1:8080/api/v1/jobs/job_0002/flows/source-to-film"
    body = json.loads(call["body"].decode("utf-8"))
    assert body == {
        "target_duration_sec": 20,
        "default_shot_seconds": 5,
        "acceleration_profile": "lightx2v-h3-4step",
        "width": 1280,
        "height": 720,
        "language": "zh-Hant",
        "visual_style": ["cinematic live action", "warm desert fantasy"],
        "world_rules": ["same Aladdin", "same brass lamp"],
    }


def test_start_source_to_film_rejects_wrong_os_job_provenance():
    client, _ = make_client({
        "os_project_id": "prj_0002",
        "os_job_id": "job_other",
        "studio_project_id": "os-job_other",
        "studio_source_id": "source",
        "queue_id": "q",
        "artifact": {"id": "art"},
    })

    with pytest.raises(EngineeringOSContractError, match="os_job_id"):
        client.start_source_to_film(job_id="job_0002")


def test_start_source_to_film_requires_os_provenance_artifact():
    client, _ = make_client({
        "os_project_id": "prj_0002",
        "os_job_id": "job_0002",
        "studio_project_id": "os-job_0002",
        "studio_source_id": "source",
        "queue_id": "q",
    })

    with pytest.raises(EngineeringOSContractError, match="provenance artifact"):
        client.start_source_to_film(job_id="job_0002")


def test_start_source_to_film_validates_dimensions_before_transport():
    client, transport = make_client({})
    with pytest.raises(ValueError, match="width and height"):
        client.start_source_to_film(job_id="job_0002", width=0, height=720)
    assert transport.calls == []
