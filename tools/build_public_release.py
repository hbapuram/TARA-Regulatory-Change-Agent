"""Build a reviewed public-release candidate without private Git history.

This tool copies only allowlisted paths, runs the public quality gates, scans
for common secret formats, and writes SHA-256 hashes. It never creates a Git
repository and never pushes anything.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import subprocess
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = ROOT.parent / "tara-public-release"
MANIFEST = ROOT / "public-release-manifest.txt"

FORBIDDEN_PARTS = {
    ".git", ".pytest_cache", "__pycache__", ".venv", "venv", "review",
    "Claude outputs", "tara.egg-info",
}
FORBIDDEN_SUFFIXES = {".pyc", ".db", ".sqlite", ".sqlite3", ".jsonl", ".pem", ".key"}
SECRET_PATTERNS = {
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "GitHub token": re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{30,}\b"),
    "OpenAI-style key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
}


def entries() -> list[str]:
    return [
        line.strip()
        for line in MANIFEST.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def forbidden(path: Path) -> bool:
    rel = path.relative_to(ROOT)
    return bool(set(rel.parts) & FORBIDDEN_PARTS) or path.suffix.lower() in FORBIDDEN_SUFFIXES


def copy_allowlist(output: Path) -> None:
    for relative in entries():
        source = ROOT / relative
        if not source.exists():
            raise SystemExit(f"manifest path does not exist: {relative}")
        if source.is_symlink():
            raise SystemExit(f"symlinks are not allowed in the public release: {relative}")
        if source.is_dir():
            for item in source.rglob("*"):
                if not item.is_file() or item.is_symlink() or forbidden(item):
                    continue
                destination = output / item.relative_to(ROOT)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, destination)
        else:
            if forbidden(source):
                raise SystemExit(f"forbidden manifest entry: {relative}")
            destination = output / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)


def scan_secrets(output: Path) -> None:
    findings: list[str] = []
    for path in output.rglob("*"):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(text):
                findings.append(f"{path.relative_to(output)}: {label}")
    if findings:
        raise SystemExit("secret scan failed:\n" + "\n".join(findings))


def remove_generated_state(output: Path) -> None:
    """Delete files that quality gates may create but releases must not ship."""
    for path in list(output.rglob("*")):
        if path.is_file() and (
            path.suffix.lower() in FORBIDDEN_SUFFIXES
            or path.name.startswith("graph_version") and path.suffix == ".json"
        ):
            path.unlink()
    for name in ("__pycache__", ".pytest_cache", "tara.egg-info"):
        for path in sorted(output.rglob(name), reverse=True):
            if path.is_dir():
                shutil.rmtree(path)


def audit_candidate(output: Path) -> None:
    offenders = [
        str(path.relative_to(output))
        for path in output.rglob("*")
        if set(path.relative_to(output).parts) & FORBIDDEN_PARTS
        or (path.is_file() and path.suffix.lower() in FORBIDDEN_SUFFIXES)
    ]
    if offenders:
        raise SystemExit("forbidden public-release paths:\n" + "\n".join(offenders))


def run_quality_gates(output: Path) -> None:
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    subprocess.run(
        ["pytest", "-q", "-p", "no:cacheprovider"],
        cwd=output,
        env=env,
        check=True,
    )
    subprocess.run(["node", "--check", "demo/app.js"], cwd=output, check=True)


def write_hashes(output: Path) -> None:
    rows: list[str] = []
    for path in sorted(p for p in output.rglob("*") if p.is_file()):
        if path.name == "RELEASE_MANIFEST.sha256":
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        rows.append(f"{digest}  {path.relative_to(output).as_posix()}")
    (output / "RELEASE_MANIFEST.sha256").write_text("\n".join(rows) + "\n", encoding="utf-8")


def write_review_note(output: Path) -> None:
    text = f"""# Public release integrity note

Built {date.today().isoformat()} from the explicit allowlist in
`public-release-manifest.txt`. This directory has **no `.git` folder** and
contains no private repository history.

## What the release process checked

- The canonical test suite passed inside this clean snapshot.
- JavaScript syntax checks passed.
- Common secret patterns and generated private state were excluded.
- `RELEASE_MANIFEST.sha256` records a digest for every released file.
- The repository is released under the MIT License.

The working repository's commits and messages are intentionally not copied by
this process. This public repository begins with one reviewed release commit.
"""
    (output / "PUBLIC_RELEASE_REVIEW.md").write_text(text, encoding="utf-8")


def prepare_output(output: Path) -> None:
    """Create or safely replace a directory owned by this release builder."""
    output = output.resolve()
    if output == ROOT or ROOT in output.parents:
        raise ValueError("output must be outside the private repository")
    if not output.name.startswith("tara-public-release"):
        raise ValueError("output directory name must start with 'tara-public-release'")
    if output.exists():
        marker = output / "PUBLIC_RELEASE_REVIEW.md"
        if not marker.is_file():
            raise ValueError(f"refusing to delete unrecognized existing directory: {output}")
        shutil.rmtree(output)
    output.mkdir(parents=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    output = args.output.resolve()
    try:
        prepare_output(output)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    copy_allowlist(output)
    if (output / ".git").exists():
        raise SystemExit("public release must not contain Git history")
    scan_secrets(output)
    run_quality_gates(output)
    remove_generated_state(output)
    audit_candidate(output)
    write_review_note(output)
    write_hashes(output)
    scan_secrets(output)
    files = sum(1 for p in output.rglob("*") if p.is_file())
    print(f"public release candidate: {output}")
    print(f"files: {files}")
    print("history: none (.git absent)")
    print("quality gates: passed")


if __name__ == "__main__":
    main()
