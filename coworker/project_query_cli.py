"""CLI for model-facing OpenWorker project/job knowledge questions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional

from .runtimes.project_knowledge import ProjectKnowledgeStore


def main(argv: Optional[list[str]] = None) -> None:
    parser = argparse.ArgumentParser(
        prog="openworker-project-query",
        description="Query durable OpenWorker project/job work knowledge.",
    )
    parser.add_argument("--cwd", default=".", help="fixed OpenWorker workspace")
    parser.add_argument("--question", "-q", required=True, help="project/job question")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    parser.add_argument("--limit", type=int, default=8, help="maximum matched events")
    args = parser.parse_args(argv)

    workspace = Path(args.cwd).expanduser().resolve()
    result = ProjectKnowledgeStore(workspace).query(args.question, limit=max(1, args.limit))
    if args.json:
        payload = {
            "schema_version": "openworker.project-knowledge-answer.v1",
            "question": result.question,
            "answer": result.answer,
            "snapshot": {
                "project_id": result.snapshot.project_id,
                "project_code": result.snapshot.project_code,
                "job_id": result.snapshot.job_id,
                "job_code": result.snapshot.job_code,
                "assigned_host": result.snapshot.assigned_host,
                "workspace_root": result.snapshot.workspace_root,
                "mission_id": result.snapshot.mission_id,
                "user_goal": result.snapshot.user_goal,
                "current_stage": result.snapshot.current_stage,
                "current_status": result.snapshot.current_status,
                "current_owner": result.snapshot.current_owner,
                "current_capability": result.snapshot.current_capability,
                "latest_summary": result.snapshot.latest_summary,
                "blockers": list(result.snapshot.blockers),
                "decisions": list(result.snapshot.decisions),
                "next_actions": list(result.snapshot.next_actions),
                "evidence": list(result.snapshot.evidence),
                "event_count": result.snapshot.event_count,
            },
            "matched_events": [
                {
                    "sequence": event.sequence,
                    "timestamp": event.timestamp,
                    "kind": event.kind,
                    "stage": event.stage,
                    "summary": event.summary,
                    "status": event.status,
                    "owner": event.owner,
                    "capability_id": event.capability_id,
                    "evidence": list(event.evidence),
                    "blockers": list(event.blockers),
                    "decisions": list(event.decisions),
                    "next_actions": list(event.next_actions),
                    "details": event.details,
                }
                for event in result.matched_events
            ],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return
    print(result.answer)


if __name__ == "__main__":
    main()
