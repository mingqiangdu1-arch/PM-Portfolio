from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
API_ROOT = REPOSITORY_ROOT / "services" / "api"
OUTPUT = REPOSITORY_ROOT / "packages" / "contracts" / "openapi" / "openapi.json"


def render_contract() -> str:
    sys.path.insert(0, str(API_ROOT))
    from app.main import app

    return json.dumps(app.openapi(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate the canonical OpenAPI contract")
    parser.add_argument("--check", action="store_true", help="fail if committed output differs")
    args = parser.parse_args()
    rendered = render_contract()
    if args.check:
        if not OUTPUT.exists() or OUTPUT.read_text(encoding="utf-8") != rendered:
            print(f"OpenAPI contract is stale: {OUTPUT}", file=sys.stderr)
            return 1
        print(f"OpenAPI contract is current: {OUTPUT}")
        return 0
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    # Write canonical UTF-8 bytes directly so Windows does not translate the
    # contract's LF newlines to CRLF and change its published SHA256.
    OUTPUT.write_bytes(rendered.encode("utf-8"))
    print(f"Generated {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
