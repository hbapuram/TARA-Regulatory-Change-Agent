"""Builds tools/dashboard.html by injecting a fresh pipeline snapshot into
tools/dashboard_template.html. No server — open the output file directly
in a browser.

    python tools/build_dashboard.py

dashboard.html and demo_data.json are generated (gitignored); only the
template and this script are source.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = REPO_ROOT / "tools"
sys.path.insert(0, str(TOOLS_DIR))

from export_demo_data import build_snapshot  # noqa: E402


def main() -> None:
    snapshot = build_snapshot()
    (TOOLS_DIR / "demo_data.json").write_text(
        json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8"
    )

    template = (TOOLS_DIR / "dashboard_template.html").read_text(encoding="utf-8")
    minified = json.dumps(snapshot, separators=(",", ":"))
    if "__DEMO_DATA_JSON__" not in template:
        raise SystemExit("dashboard_template.html is missing the __DEMO_DATA_JSON__ placeholder")
    output = template.replace("__DEMO_DATA_JSON__", minified)

    out_path = TOOLS_DIR / "dashboard.html"
    out_path.write_text(output, encoding="utf-8")
    print(f"wrote {out_path} ({len(output):,} bytes)")


if __name__ == "__main__":
    main()
