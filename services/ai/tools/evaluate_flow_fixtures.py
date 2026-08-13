"""Evaluate fixed Flow JSON fixtures without converting or rendering them."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "flow_spike" / "fixtures"


def evaluate_fixture(fixture: dict) -> dict:
    nodes = {node["id"]: node for node in fixture["nodes"]}
    adjacency = {node_id: [] for node_id in nodes}
    logic_errors: list[str] = []
    for edge in fixture["edges"]:
        if edge["from"] not in nodes or edge["to"] not in nodes:
            logic_errors.append(f"dangling_edge:{edge['from']}->{edge['to']}")
            continue
        adjacency[edge["from"]].append(edge["to"])

    starts = [node_id for node_id, node in nodes.items() if node["type"] == "start"]
    reachable: set[str] = set()
    pending = list(starts)
    while pending:
        node_id = pending.pop()
        if node_id in reachable:
            continue
        reachable.add(node_id)
        pending.extend(adjacency.get(node_id, []))
    for node_id in sorted(nodes.keys() - reachable):
        logic_errors.append(f"orphan_node:{node_id}")

    actual = {
        "reachable_nodes": len(reachable),
        "decision_nodes": sum(node["type"] == "decision" for node in nodes.values()),
        "terminal_nodes": sum(node["type"] == "end" for node in nodes.values()),
        "logic_errors": sorted(logic_errors),
    }
    expected = fixture["expected"]
    comparable_expected = {key: expected[key] for key in actual}
    recovery = expected.get("recovery_edge")
    recovery_present = recovery is None or recovery in fixture["edges"]
    return {
        "fixture_id": fixture["fixture_id"],
        "passed": actual == comparable_expected and recovery_present,
        "actual": actual,
        "expected": comparable_expected,
        "recovery_present": recovery_present,
    }


def main() -> int:
    results = []
    for path in sorted(FIXTURE_DIR.glob("*.json")):
        raw = path.read_bytes()
        fixture = json.loads(raw.decode("utf-8"))
        result = evaluate_fixture(fixture)
        result["file"] = path.name
        result["sha256"] = sha256(raw).hexdigest()
        results.append(result)
    passed = len(results) == 3 and all(item["passed"] for item in results)
    print(json.dumps({"passed": passed, "results": results}, ensure_ascii=False, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
