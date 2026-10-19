# Plan: hosted evaluation with Anthropic API keys

The first public release supports hosted PennyRouter through a signed-in Claude
subscription (`claude-login`). API-key evaluation is planned and is not advertised.

## How it should work

The user connects an Anthropic API key to their PennyRouter account, either by selecting
it during `npx pennyrouter install` or at <https://pennyrouter.com/keys>. PennyRouter then
holds the provider key.

- Native arm: Claude Code sends the Anthropic key directly to Anthropic, as today.
- Proxy arm: Claude Code sends only the PennyRouter key (`pr-...`) as `x-api-key` to the
  hosted endpoint. The Anthropic key is never sent to PennyRouter; the gateway uses the
  stored one upstream.

Both arms use the same auth profile, so the one-variable check still sees a route-only
change. The two keys never travel in the same request, so there is no `x-api-key`
collision.

## What was checked

- The gateway treats a `pr-` key on `x-api-key` as the caller's credential
  (`auth_anthropic` in `apps/gateway/pennyrouter/main.py`), so no gateway change is needed
  to authenticate the proxy arm.
- A raw `sk-ant-` key on `x-api-key` matches no `pr-` row and falls through as an
  unidentified caller. Sending the Anthropic key to the hosted endpoint is therefore not
  a supported path; this is why the current `api_key` proxy arm cannot work as written.
- Not yet verified: that the hosted gateway uses the stored Anthropic key for a
  `pr-`-keyed Claude Code request on an account with no linked subscription. The keys page
  labels it an "Anthropic API fallback for Claude Code"; confirm with a one-task run.

## Steps

1. **Runner change: done.** `pennybench/agent_env.py` builds the proxy arm's environment
   from the endpoint key alone when an `api_key` profile meets an endpoint with `key_env`;
   the provider key is never read for that arm. Unit tests cover both arms' environments
   and the missing-variable errors.
2. **Audit: covered structurally.** The proxy arm's environment never contains the
   provider key, and `secret_leaks` scans artifacts for the endpoint key. No separate
   wire audit was added.
3. **Verify: client side done, gateway side open.** A one-pair smoke (2026-10-19, Haiku,
   fizzbuzz, isolated root) completed with both arms at reward 1.0 and a passing audit.
   The native arm sent only the Anthropic key, only to `api.anthropic.com`; the proxy arm
   sent only the `pr-` key, only to `api.pennyrouter.com`, and received 200s. Still to
   confirm from gateway records: that PennyRouter used the account's stored Anthropic
   key for those requests. Also repeat on a clean checkout with a different user's account.
4. **Docs: partly done.** `docs/CREDENTIALS.md` describes the flow as experimental. After
   step 3, add the install/keys steps to the README quick start and drop the
   "experimental" label. Label API-key and subscription results separately.
