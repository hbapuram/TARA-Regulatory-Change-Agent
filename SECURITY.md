# Security policy

## Prototype status

TARA is a stateless competition prototype. The public demo is not designed to receive real personal, legal, tax, immigration, financial, or filing data.

## Report a vulnerability

Do not open a public issue containing exploit details, credentials, or personal data. Contact the repository owner privately through the security-reporting channel available on the GitHub repository.

Include the affected component, reproduction steps, expected impact, and any suggested mitigation. Please allow reasonable time for triage before disclosure.

## Supported surface

Security fixes are applied to the latest `main` branch. The demo has no production authentication, durable tenant storage, or service-level guarantee. Generated replay data and checked-in registers must contain synthetic data only.

## Secrets

Never commit API keys, tokens, cookies, passwords, private keys, or populated `.env` files. Use `.env.example` only for variable names and documentation.
