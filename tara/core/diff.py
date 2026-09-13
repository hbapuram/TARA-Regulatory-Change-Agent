"""Structural diffing over named, versioned regulatory sources.

Deliberately dumb: ``difflib`` only, no model call. SURVEY's job is to say
*what* changed and *where* (by provision heading), not to interpret it —
interpretation is LEGEND's job, working from the structured output here.
"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field

_SECTION_HEADING = re.compile(r"^Section\s+(\d+\.\d+)\s*(?:—|-)?\s*(.*)$")


@dataclass(frozen=True)
class Provision:
    reference: str          # e.g. "Section 4.3"
    heading: str
    text: str


@dataclass(frozen=True)
class ProvisionChange:
    reference: str
    heading: str
    before: str | None      # None if the provision is new
    after: str | None       # None if the provision was withdrawn
    unified_diff: str = field(repr=False)

    @property
    def change_type(self) -> str:
        if self.before is None:
            return "added"
        if self.after is None:
            return "removed"
        return "amended"


def split_into_provisions(document_text: str) -> dict[str, Provision]:
    """Split a source document into provisions keyed by their section
    reference, using ``Section N.N`` headings as boundaries.
    """
    lines = document_text.splitlines()
    provisions: dict[str, Provision] = {}
    current_ref = None
    current_heading = ""
    buffer: list[str] = []

    def flush():
        if current_ref is not None:
            text = "\n".join(buffer).strip()
            provisions[current_ref] = Provision(current_ref, current_heading, text)

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("Last verified:"):
            # Document footer/metadata, not part of any provision's body —
            # stop here so it never gets attributed to the last section and
            # falsely reported as a content change.
            break
        match = _SECTION_HEADING.match(stripped)
        if match:
            flush()
            current_ref = f"Section {match.group(1)}"
            current_heading = match.group(2).strip()
            buffer = [line]
        else:
            buffer.append(line)
    flush()
    return provisions


def diff_documents(v1_text: str, v2_text: str) -> list[ProvisionChange]:
    """Diff two versions of the same source at provision granularity.

    Returns only provisions whose text actually changed (or that were added
    or removed) — unchanged provisions are not reported. This is what makes
    ALMANAC's later "reached and unchanged" coverage assertion meaningful:
    an empty result here is a real finding, not a crawl failure.
    """
    before_provisions = split_into_provisions(v1_text)
    after_provisions = split_into_provisions(v2_text)

    all_refs = sorted(set(before_provisions) | set(after_provisions))
    changes: list[ProvisionChange] = []

    for ref in all_refs:
        before = before_provisions.get(ref)
        after = after_provisions.get(ref)
        before_text = before.text if before else None
        after_text = after.text if after else None

        if before_text == after_text:
            continue

        unified = "\n".join(
            difflib.unified_diff(
                (before_text or "").splitlines(),
                (after_text or "").splitlines(),
                fromfile=f"{ref} (v1)",
                tofile=f"{ref} (v2)",
                lineterm="",
            )
        )
        heading = (after or before).heading
        changes.append(ProvisionChange(ref, heading, before_text, after_text, unified))

    return changes
