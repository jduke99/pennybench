# Credentials, tasks and publication safety

Do not post secrets or sensitive raw artifacts in a public issue. Report
vulnerabilities privately to jon@pennyrouter.com, or use the repository's private
vulnerability-reporting channel when available. Do not include secrets in the report.

The following remain private by default:

- `.env`, `pennybench.local.toml`, subscription credentials and provider/Penny keys.
- `runs/`, downloaded datasets, credential copies, Docker caches and local logs.
- Unreviewed wire requests/responses, task files, account identifiers and transcripts.

Credentials are exposed to task code inside containers during a trial. Use trusted
tasks and appropriately scoped/dedicated credentials. Runtime secret scanning and
credential-copy cleanup are safeguards, not a guarantee that arbitrary task code is safe.

Capture files include prompts, outputs and metadata, even when authentication headers
are redacted. Review and sanitize them separately before sharing. Ignoring files does
not remove them from Git history. If a real credential was committed, rotate/revoke it
first; coordinate any history rewrite with the maintainer rather than doing it silently.

Only reviewed aggregate results and provenance should be copied into public result
directories. Dataset, harness and third-party skill licenses still apply.
