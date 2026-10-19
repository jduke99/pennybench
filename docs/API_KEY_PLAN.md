# Plan: hosted evaluation with API keys

The first public release supports hosted PennyRouter through a signed-in Claude
subscription (`claude-login`): the gateway identifies the user's linked account, so the
runner sends no separate Penny key. API-key profiles are rejected for proxy arms with a
separate endpoint key because the model credential and the endpoint credential both use
`x-api-key`.

Do not advertise API-key hosted evaluation until the steps below are done.

1. **Decide the wire contract.** Options: (a) gateway accepts the endpoint key in a
   dedicated header (e.g. `X-Penny-Key`) while `x-api-key` carries the Anthropic key;
   (b) endpoint key in `Authorization: Bearer`, Anthropic key in `x-api-key`. Prefer (a)
   and confirm the gateway already forwards `x-api-key` upstream untouched.
2. **Gateway change** (penny-router, separate review): accept the dedicated header, keep
   current behaviour when absent, add tests for both-credential requests.
3. **Runner change:** inject the header from `key_env`; drop the collision rejection for
   hosted endpoints that advertise support; keep rejection for private endpoints that do
   not. Add unit tests for header injection and the rejection path.
4. **Audit:** extend the audit so a dual-auth trial proves the model call reached the
   declared host and that neither credential appears in captures or logs
   (`secret_leaks` stays empty).
5. **Validate** with a one-task smoke on a clean checkout using a separate account, then
   update `docs/CREDENTIALS.md` and the README quick start.
