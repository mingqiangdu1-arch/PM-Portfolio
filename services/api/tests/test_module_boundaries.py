import ast
import unittest
from pathlib import Path


API_ROOT = Path(__file__).resolve().parents[1] / "app"
MODULES_ROOT = API_ROOT / "modules"
EXPECTED_MODULES = {
    "identity",
    "projects",
    "files",
    "requirements",
    "prds",
    "reviews",
    "confirmation",
    "validation",
    "ai_tasks",
    "sprint1",
}


class ModuleBoundaryTests(unittest.TestCase):
    def test_expected_sprint_zero_boundaries_exist(self) -> None:
        # The old Sprint 0 fixture named an ``artifacts`` module.  The current
        # authoritative API boundary owns PRD and Requirement domains
        # separately, while Sprint 1 application services remain under the
        # explicit ``sprint1`` boundary.
        actual = {path.name for path in MODULES_ROOT.iterdir() if path.is_dir()}
        self.assertTrue(EXPECTED_MODULES.issubset(actual))

    def test_http_adapters_do_not_import_database_adapters(self) -> None:
        violations: list[str] = []
        for source in (API_ROOT / "api").rglob("*.py"):
            tree = ast.parse(source.read_text(encoding="utf-8"))
            imports = [
                node.module or ""
                for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom)
            ]
            if any("repository" in name or ".db" in name for name in imports):
                violations.append(str(source))
        self.assertEqual(violations, [])
