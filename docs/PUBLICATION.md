# Incremental public-repository preparation

This checklist prepares PennyBench for a public repository. It is not authorization
to publish, push, change visibility, rewrite history, or stop running jobs.

## First increment

- [x] Hosted-first quick start and example endpoint: `https://api.pennyrouter.com`.
- [x] Explain personal subscriptions, token profiles, API-key limitations and custom servers.
- [x] Keep one shared runner and introduce suite-specific SkillsBench config copies.
- [x] Preserve historical experiment/report paths and active Terminal-Bench files.
- [x] Add SkillsBench provenance and source verification without running tasks.
- [x] Keep pricing JSON in distributable runner packages.

## Before release

- [ ] Finish and review the Terminal-Bench study in the separate evaluation workflow.
- [ ] Verify subscription onboarding on a clean checkout with a separate user's own account.
- [ ] Hosted API-key evaluation: runner done; verify one real run (`docs/API_KEY_PLAN.md` step 3). Not advertised until then.
- [x] Repository license (Apache-2.0, copyright Jon Duke) and security contact (jon@pennyrouter.com).
- [ ] Confirm no employer or university claims the rights to this repository's contents.
- [ ] Verify attribution and redistribution rights for Harbor, datasets and bundled skills.
- [ ] Audit all tracked files AND history for credentials, account IDs, personal paths,
      private endpoints and raw captures. Do not print found secret values into logs.
- [ ] Review report exports, task selection, exclusions, provenance and reproduction commands.
- [ ] Decide the final suite result locations; preserve historical paths or references.
- [ ] Validate source installation and the built wheel from a clean environment.
- [ ] Add reviewed CI using unit tests only, without credentials or model/Docker jobs.
- [ ] Review the final diff and commit preparation changes with approval.
- [ ] Approve publication separately; do not include private `runs/` artifacts in the release.

The current root `experiments/` remains a historical compatibility path. No live
Terminal-Bench source, active configuration, run lock, process or container is moved by
this increment. The real private `pennybench.local.toml` and `.env` are not rewritten.
