import json
from pathlib import Path

from tools.evaluate_flow_gate import evaluate

ROOT = Path(__file__).resolve().parents[1]


def rubric() -> dict:
    return json.loads((ROOT / "flow_spike" / "rubric.json").read_text(encoding="utf-8"))


def test_missing_gate_results_fail_closed() -> None:
    passed, score, failed = evaluate(rubric(), {"checks": {}})
    assert passed is False
    assert score == 0
    assert set(failed) == {item["id"] for item in rubric()["mandatory_checks"]}


def test_gate_passes_only_when_every_mandatory_check_passes() -> None:
    checks = {item["id"]: True for item in rubric()["mandatory_checks"]}
    passed, score, failed = evaluate(rubric(), {"checks": checks})
    assert passed is True
    assert score == 100
    assert failed == []
