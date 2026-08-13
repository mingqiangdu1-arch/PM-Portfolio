"""Run deterministic event-quality checks over a JSON array."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from dataclasses import asdict
from pathlib import Path

from app.data_quality import inspect_events


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("event_file", type=Path)
    parser.add_argument("--known-task-id", action="append", default=[])
    parser.add_argument("--known-user-id", action="append", default=[])
    parser.add_argument("--known-project-id", action="append", default=[])
    parser.add_argument("--known-project-version-id", action="append", default=[])
    parser.add_argument("--known-file-version-id", action="append", default=[])
    parser.add_argument("--now", help="Optional RFC3339 quality-window time for future timestamp checks")
    args = parser.parse_args()
    events = json.loads(args.event_file.read_text(encoding="utf-8"))
    known_ids = {
        key: set(values)
        for key, values in {
            "user_id": args.known_user_id,
            "project_id": args.known_project_id,
            "project_version_id": args.known_project_version_id,
            "file_version_id": args.known_file_version_id,
        }.items()
        if values
    }
    report = inspect_events(
        events,
        known_task_ids=set(args.known_task_id) if args.known_task_id else None,
        known_ids=known_ids,
        now=datetime.fromisoformat(args.now.replace("Z", "+00:00")) if args.now else None,
    )
    print(json.dumps(asdict(report), ensure_ascii=False, indent=2))
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
