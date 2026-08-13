import json
from pathlib import Path

from tools.evaluate_flow_fixtures import evaluate_fixture

ROOT = Path(__file__).resolve().parents[1]


def test_all_three_fixed_flow_samples_match_expectations() -> None:
    paths = sorted((ROOT / "flow_spike" / "fixtures").glob("*.json"))
    results = [evaluate_fixture(json.loads(path.read_text(encoding="utf-8"))) for path in paths]
    assert len(results) == 3
    assert all(result["passed"] for result in results)
    assert any("orphan_node:orphan" in result["actual"]["logic_errors"] for result in results)
