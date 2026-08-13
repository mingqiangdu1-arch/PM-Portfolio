import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


class OpsDryRunTests(unittest.TestCase):
    def run_script(self, name: str, *arguments: str) -> str:
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(ROOT / "infra" / "scripts" / name),
                *arguments,
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return result.stdout

    def test_backup_dry_run(self) -> None:
        self.assertIn("DRY-RUN", self.run_script("backup.ps1"))

    def test_restore_dry_run(self) -> None:
        self.assertIn("DRY-RUN", self.run_script("restore.ps1", "-BackupPath", "."))

    def test_release_dry_run_rejects_latest(self) -> None:
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(ROOT / "infra" / "scripts" / "release.ps1"),
                "-ImageTag",
                "api:latest",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        self.assertNotEqual(result.returncode, 0)

    def test_production_data_services_have_no_ports(self) -> None:
        production = (ROOT / "infra" / "compose" / "compose.production.yaml").read_text(encoding="utf-8")
        for service in ("mysql", "redis", "minio"):
            self.assertRegex(production, rf"(?ms)^  {service}:\n    ports: \[\]")

    def test_images_are_pinned(self) -> None:
        base = (ROOT / "infra" / "compose" / "compose.yaml").read_text(encoding="utf-8")
        self.assertNotRegex(base, r"(?m)^\s*image:\s*[^\s]+:latest\s*$")

    def test_environment_template_has_unique_keys(self) -> None:
        lines = (ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
        keys = [line.split("=", 1)[0] for line in lines if line and not line.startswith("#")]
        self.assertEqual(len(keys), len(set(keys)))


if __name__ == "__main__":
    unittest.main()
