# Public release integrity note

Built 2026-09-13 from the explicit allowlist in
`public-release-manifest.txt`. This directory has **no `.git` folder** and
contains no private repository history.

## What the release process checked

- The canonical test suite passed inside this clean snapshot.
- The executable evaluation card was regenerated from the snapshot.
- JavaScript syntax checks passed.
- Common secret patterns and generated private state were excluded.
- `RELEASE_MANIFEST.sha256` records a digest for every released file.
- The repository is released under the MIT License.

The working repository's commits and messages are intentionally not copied by
this process. This public repository begins with one reviewed release commit.
