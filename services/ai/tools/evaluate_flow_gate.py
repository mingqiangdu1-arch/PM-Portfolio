"""Evaluate recorded Flow Spike evidence without invoking conversion tools."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def evaluate(rubric: dict, evidence: dict) -> tuple[bool, int, list[str]]:
    check_results = evidence.get("checks", {})
    failed = [
        item["id"]
        for item in rubric["mandatory_checks"]
        if check_results.get(item["id"]) is not True
    ]
    score = sum(
        item["points"]
        for item in rubric["mandatory_checks"]
        if check_results.get(item["id"]) is True
    )
    passed = not failed and score == rubric["pass_score"]
    return passed, score, failed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rubric", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    rubric = json.loads(args.rubric.read_text(encoding="utf-8"))
    evidence = json.loads(args.evidence.read_text(encoding="utf-8"))
    passed, score, failed = evaluate(rubric, evidence)
    print(json.dumps({"passed": passed, "score": score, "failed_checks": failed}, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
