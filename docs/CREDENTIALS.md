# Credentials and endpoint configuration

All evaluations use credentials supplied by the person running them. The published
SkillsBench experiment used a personal Claude subscription, not an API billing account.
PennyBench is not a credential or subscription service.

## Signed-in Claude subscription: the published workflow

Use `claude auth login`, then install PennyRouter with `npx pennyrouter install` and select
the Anthropic subscription. Confirm that `penny claude` starts normally; that links the same
account to PennyRouter.
Keep `auth: claude-login` in both arms and `[auth.claude-login]` in your private
`pennybench.local.toml`. The default endpoint is `https://api.pennyrouter.com`.

The runner reads Claude Code's own `claudeAiOauth` entry from the macOS Keychain or
Linux credentials file. It stages a private copy per trial, installs it into the
container's isolated Claude configuration, and removes staged and copied-back
credentials afterward. Refreshed login tokens can be synchronized back to your
credential store. Other stored sign-ins are not selected.

This workflow does not need a Penny API key in the agent environment: the hosted
gateway recognizes your linked account from the Claude login. Every switched
account must be linked too. Usage windows belong to your account; other sessions
using the account consume the same allowance.

## Subscription token profile

`kind = "oauth"` reads the environment variable named by `token_env`; the example
uses `CLAUDE_CODE_OAUTH_TOKEN`. These token-only arms behave differently from a
fully signed-in Claude Code session and are **not** the published login experiment.

For proxy routes, the runner sends the upstream token as the bearer. If the endpoint
requires its own Penny key, configure `key_env = "PENNY_API_KEY"`; that separate key
uses `x-api-key`. Keep both secrets in your ignored `.env`, not in YAML or TOML.

## Anthropic API keys

The runner supports `kind = "api_key"`, reading `ANTHROPIC_API_KEY` in the example.
Native trials send that key directly to Anthropic.

Hosted PennyRouter holds your Anthropic key itself; the agent does not send it to the
gateway. Connect the key once, either by selecting an Anthropic API key during
`npx pennyrouter install`, or at <https://pennyrouter.com/keys>. Claude Code then
authenticates to PennyRouter with your PennyRouter key, which PennyRouter issues, and
PennyRouter uses the stored Anthropic key upstream.

For an `api_key` profile, set `key_env = "PENNY_API_KEY"` on the endpoint. The proxy arm
then sends only that PennyRouter key as `x-api-key`; your Anthropic key is not read for
that arm and never reaches the endpoint or the task container. The native arm sends the
Anthropic key directly. Without `key_env`, the proxy arm sends your Anthropic key to the
endpoint, which suits a private server that accepts it but not hosted PennyRouter.

Status: the runner behavior is implemented and unit-tested. A real hosted run has not yet
confirmed that PennyRouter uses the stored key for this account (see
[API_KEY_PLAN.md](API_KEY_PLAN.md)), so treat this workflow as experimental.

Change both arms' auth profile together when designing an API-key experiment; the
one-variable check rejects an accidental route-plus-auth change. Keep subscription
and API-key results separately labeled.

## Custom endpoints

Replace `[endpoints.proxy].base_url` with the private server's HTTPS Messages API base
URL. It must be reachable from the task containers. Authentication depends on the
server: do not reuse a subscription or API key with an endpoint you do not trust.
`pennybench.local.toml` is just the runner's private configuration filename; it does
not imply a local gateway. Endpoint `env` configures the agent, not the remote server.

## Security boundaries

Task containers receive the trial credential and task code can read it. Review tasks
and consider a dedicated account/key with appropriate limits. The runner references
secrets through private environment variables instead of placing them in argv or
saved Harbor configuration, then scans retained artifacts for known secret values.
These precautions do not make untrusted task execution risk-free.

Never publish `.env`, `pennybench.local.toml`, credential copies, or unreviewed logs.
See [SECURITY.md](../SECURITY.md). Keep the endpoint URL and auth profile names in
published methodology, but never the secret values or account-identifying payloads.
