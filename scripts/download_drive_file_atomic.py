"""Download one immutable Google Drive raw file and atomically publish it locally."""
from __future__ import annotations

import argparse
import json
import platform

from coworker.drive_ingress import (
    GoogleDriveRawDownloadClient,
    ingress_drive_file_atomic,
    write_ingress_receipt,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file-id", required=True)
    parser.add_argument("--destination", required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--expected-size-bytes", required=True, type=int)
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--machine-id", default=platform.node())
    parser.add_argument("--request-id", default="")
    parser.add_argument("--run-id", default="")
    return parser


def main() -> int:
    args = _parser().parse_args()
    metadata = {
        key: value
        for key, value in {
            "request_id": str(args.request_id).strip(),
            "run_id": str(args.run_id).strip(),
        }.items()
        if value
    }
    client = GoogleDriveRawDownloadClient.from_environment()
    try:
        receipt = ingress_drive_file_atomic(
            client,
            file_id=args.file_id,
            destination=args.destination,
            expected_sha256=args.expected_sha256,
            expected_size_bytes=args.expected_size_bytes,
            machine_id=args.machine_id,
            metadata=metadata,
        )
    finally:
        client.close()
    write_ingress_receipt(receipt, args.receipt)
    print(json.dumps(receipt.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
