import json

import pytest

from coworker.engineering.engineering_os import EngineeringOSConfig, EngineeringOSContractError, TransportResponse
from coworker.engineering.source_to_film import EngineeringOSMediaClient


class SequenceTransport:
    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.calls = []

    def request(self, method, url, *, body, headers, timeout):
        self.calls.append((method, url, body))
        if not self.payloads:
            raise AssertionError("unexpected transport call")
        payload = self.payloads.pop(0)
        return TransportResponse(status=200, body=json.dumps(payload).encode("utf-8"))


def client(*payloads):
    transport = SequenceTransport(payloads)
    return EngineeringOSMediaClient(
        EngineeringOSConfig("http://127.0.0.1:8080", timeout_seconds=3),
        transport=transport,
    ), transport


def succeeded_queue(*, artifacts=True):
    output = {"artifacts": ["shot-1.mp4"]} if artifacts else {"artifacts": []}
    return {
        "os_job_id": "job_0002",
        "queue_id": "q",
        "queue": {
            "status": "succeeded",
            "items": [
                {"id": "shot.generate:shot-1", "kind": "shot.generate", "status": "succeeded", "output": output}
            ],
        },
    }


def test_source_to_film_status_calls_os_only():
    c, transport = client({
        "os_job_id": "job_0002",
        "queue_id": "q-0002",
        "queue": {"status": "running"},
    })
    result = c.source_to_film_status(job_id="job_0002")
    assert result["queue"]["status"] == "running"
    assert transport.calls == [
        ("GET", "http://127.0.0.1:8080/api/v1/jobs/job_0002/flows/source-to-film/status", None)
    ]


def test_wait_source_to_film_returns_terminal_success_without_direct_studio_access(monkeypatch):
    c, transport = client(
        {"os_job_id": "job_0002", "queue_id": "q", "queue": {"status": "running"}},
        succeeded_queue(),
    )
    monkeypatch.setattr("coworker.engineering.source_to_film.time.sleep", lambda _: None)
    result = c.wait_source_to_film(job_id="job_0002", timeout_seconds=10, poll_seconds=0.01)
    assert result["queue"]["status"] == "succeeded"
    assert all("127.0.0.1:8080" in url for _, url, _ in transport.calls)


def test_wait_source_to_film_rejects_false_green_without_shots():
    c, _ = client({
        "os_job_id": "job_0002",
        "queue_id": "q",
        "queue": {"status": "succeeded", "items": [{"id": "character.prepare:a", "kind": "character.prepare", "status": "succeeded"}]},
    })
    with pytest.raises(EngineeringOSContractError, match="shot.generate"):
        c.wait_source_to_film(job_id="job_0002", timeout_seconds=10, poll_seconds=0.01)


def test_wait_source_to_film_rejects_false_green_without_shot_artifact():
    c, _ = client(succeeded_queue(artifacts=False))
    with pytest.raises(EngineeringOSContractError, match="no artifact"):
        c.wait_source_to_film(job_id="job_0002", timeout_seconds=10, poll_seconds=0.01)


def test_status_rejects_missing_queue_contract():
    c, _ = client({"os_job_id": "job_0002", "queue_id": "q", "queue": {}})
    with pytest.raises(Exception, match="status"):
        c.source_to_film_status(job_id="job_0002")
