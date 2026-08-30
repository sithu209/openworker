"""Publish an existing OpenWorker review bundle to Google Drive.

Default mode binds the published receipt to WorkLedger for formal review revisions.
Use --direct only for intermediate immutable review evidence that must not mutate
WorkLedger.  If no review root folder is configured, publication uses the
authenticated account's My Drive root so local-supervisor artifact return does not
silently depend on a GitHub transport or a pre-created cloud folder.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
from pathlib import Path

from coworker.review_drive import GoogleDriveAPIClient, publish_review_bundle
from coworker.review_drive_ledger import publish_review_bundle_to_ledger
from coworker.work_ledger import WorkLedger


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--revision-id", required=True)
    parser.add_argument("--work-code", required=True)
    parser.add_argument("--bundle")
    parser.add_argument("--ledger")
    parser.add_argument("--direct", action="store_true", help="publish immutable intermediate review evidence without WorkLedger mutation")
    parser.add_argument(
        "--drive-folder-id",
        default=os.environ.get("OPENWORKER_REVIEW_DRIVE_FOLDER_ID", "").strip() or "root",
    )
    parser.add_argument("--machine-id", default=platform.node())
    parser.add_argument("--case-id", default="")
    parser.add_argument("--job-id", default="")
    parser.add_argument("--run-id", default="")
    return parser


def main() -> int:
    args = _parser().parse_args()
    workspace = Path(args.workspace).expanduser().resolve()
    revision_id = str(args.revision_id).strip()
    bundle = Path(args.bundle).expanduser().resolve() if args.bundle else workspace / ".openworker" / "reviews" / revision_id
    if bundle.name != revision_id:
        raise ValueError(f"bundle directory name {bundle.name!r} does not match revision id {revision_id!r}")
    metadata = {
        key: value
        for key, value in {
            "case_id": str(args.case_id).strip(),
            "job_id": str(args.job_id).strip(),
            "run_id": str(args.run_id).strip(),
            "publication_mode": "direct" if args.direct else "ledger",
            "review_consumer": "chatgpt-drive-connector",
        }.items()
        if value
    }

    if args.direct:
        client = GoogleDriveAPIClient.from_environment()
        try:
            receipt = publish_review_bundle(
                bundle,
                work_code=args.work_code,
                root_folder_id=args.drive_folder_id,
                uploader=client,
                machine_id=args.machine_id,
                metadata=metadata,
            )
        finally:
            client.close()
    else:
        ledger_path = Path(args.ledger).expanduser().resolve() if args.ledger else workspace / ".openworker" / "work-ledger.sqlite"
        ledger = WorkLedger(ledger_path)
        try:
            receipt = publish_review_bundle_to_ledger(
                ledger,
                revision_id,
                bundle,
                work_code=args.work_code,
                root_folder_id=args.drive_folder_id,
                machine_id=args.machine_id,
                metadata=metadata,
            )
        finally:
            ledger.close()

    print(json.dumps(receipt.to_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
