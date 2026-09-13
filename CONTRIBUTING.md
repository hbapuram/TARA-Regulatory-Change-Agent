# Contributing to TARA

TARA is a competition prototype in a high-consequence domain. Contributions are welcome, but a persuasive result is not enough: changes must be traceable, deterministic where consequential, and explicit about their evidence boundary.

## Before opening a pull request

1. Explain the user problem in plain language.
2. Identify every authoritative source used and the date it was checked.
3. Put domain judgement in a domain pack rather than agent code whenever possible.
4. Add tests for the positive case, negative case, missing-fact case, and any effective-date boundary.
5. Run:

```bash
pytest -q
node --check demo/app.js
python tools/build_evaluation_card.py
python tools/build_public_release.py --output /tmp/tara-public-release
```

## Domain-pack rules

A new or changed obligation must have a stable identifier, provision, source, plain-language text, severity, evidence type, and any dependencies. Use `effective_from` / `effective_to` for historical versions and `applies_when` for obligation-specific instrument, event, or threshold facts. Missing material facts must result in `indeterminate`, never a guessed action.

## Safety boundary

Do not describe TARA output as legal, tax, immigration, or filing advice. Never add real personal data to fixtures, presets, replay files, screenshots, or documentation. Do not commit credentials, tokens, `.env` files, production logs, or private review material.

## Review expectation

Code review is necessary but not sufficient for a production domain pack. Legal or regulatory content also requires review by an appropriately qualified domain professional before real-world use.
