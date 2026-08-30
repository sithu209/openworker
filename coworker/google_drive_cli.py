"""CLI for OpenWorker Google Drive local transport."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .google_drive_transport import (
    DEFAULT_DRIVE_FOLDER_ID,
    GoogleDriveTransport,
    GoogleDriveTransportError,
    build_upload_receipt,
    deterministic_zip,
    write_receipt,
)


def _folder_id(value: str | None) -> str:
    return str(value or os.environ.get("OPENWORKER_GOOGLE_DRIVE_REVIEW_FOLDER_ID") or DEFAULT_DRIVE_FOLDER_ID).strip()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="openworker-drive")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("auth-check")

    upload = sub.add_parser("upload")
    upload.add_argument("source")
    upload.add_argument("--folder-id")
    upload.add_argument("--name")
    upload.add_argument("--description", default="")
    upload.add_argument("--receipt")

    ls = sub.add_parser("list")
    ls.add_argument("--folder-id")
    ls.add_argument("--name", default="")

    download = sub.add_parser("download")
    download.add_argument("file_id")
    download.add_argument("--output", required=True)

    review = sub.add_parser("review-publish")
    review.add_argument("source")
    review.add_argument("--work-code", required=True)
    review.add_argument("--folder-id")
    review.add_argument("--name")
    review.add_argument("--receipt")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        transport = GoogleDriveTransport()
        if args.command == "auth-check":
            print(json.dumps(transport.auth_check(), ensure_ascii=False, indent=2, sort_keys=True))
            return 0

        if args.command == "upload":
            upload = transport.upload_file(
                args.source,
                folder_id=_folder_id(args.folder_id),
                name=args.name,
                description=args.description,
            )
            receipt = build_upload_receipt(upload)
            if args.receipt:
                write_receipt(args.receipt, receipt)
            print(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True))
            return 0

        if args.command == "list":
            result = transport.list_files(folder_id=_folder_id(args.folder_id), name=args.name)
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
            return 0

        if args.command == "download":
            result = transport.download_file(args.file_id, args.output)
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
            return 0

        if args.command == "review-publish":
            source = Path(args.source).expanduser().resolve()
            temp_zip: Path | None = None
            upload_source = source
            try:
                if source.is_dir():
                    temp_zip = deterministic_zip(source)
                    upload_source = temp_zip
                name = args.name or (f"{args.work_code}-{source.name}.zip" if source.is_dir() else source.name)
                upload = transport.upload_file(
                    upload_source,
                    folder_id=_folder_id(args.folder_id),
                    name=name,
                    description=f"OpenWorker review publish work_code={args.work_code}",
                )
                receipt = build_upload_receipt(upload, status="READY_FOR_CHATGPT_REVIEW")
                receipt["work_code"] = args.work_code
                receipt["review_source_path"] = str(source)
                receipt["review_source_kind"] = "directory_zip" if source.is_dir() else "file"
                if args.receipt:
                    write_receipt(args.receipt, receipt)
                print(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True))
                return 0
            finally:
                if temp_zip and temp_zip.exists():
                    temp_zip.unlink()

        raise GoogleDriveTransportError(f"unsupported command: {args.command}")
    except GoogleDriveTransportError as exc:
        print(f"OPENWORKER_DRIVE_FAIL {exc}", file=os.sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
