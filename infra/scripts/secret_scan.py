from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCAN_ROOTS = [ROOT / "services" / "api", ROOT / "infra", ROOT / "packages", ROOT / ".github"]
ROOT_FILES = [ROOT / ".env.example", ROOT / "compose.yaml"]
SKIP_SUFFIXES = {".pyc", ".png", ".jpg", ".docx"}
PATTERNS = {
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "cloud access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "JWT": re.compile(r"\beyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}\b"),
    "secret assignment": re.compile(
        r"(?i)(?:api[_-]?key|access[_-]?token|password|secret)\s*[:=]\s*[\"'](?!\$|<|/run/secrets)[A-Za-z0-9+/=_-]{12,}[\"']"
    ),
}


def files() -> list[Path]:
    result = [path for path in ROOT_FILES if path.exists()]
    for scan_root in SCAN_ROOTS:
        if scan_root.exists():
            result.extend(path for path in scan_root.rglob("*") if path.is_file())
    return sorted(set(result))


def main() -> None:
    findings: list[str] = []
    for path in files():
        if path.suffix.lower() in SKIP_SUFFIXES or "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for label, pattern in PATTERNS.items():
            if pattern.search(text):
                findings.append(f"{path.relative_to(ROOT)}: {label}")
    if findings:
        raise SystemExit("Potential secrets detected:\n" + "\n".join(findings))
    print(f"Secret scan passed across {len(files())} files")


if __name__ == "__main__":
    main()
