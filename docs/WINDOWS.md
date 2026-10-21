# Running PennyBench on Windows (or any non-Mac host)

The runner was built and verified on an Apple Silicon Mac. Everything that runs *inside* a
trial container is Linux and portable. The host side (Harbor, mitmproxy, Docker, this package)
needs a few decisions on Windows.

## Recommended: WSL2 + Docker Desktop

Run PennyBench inside a WSL2 Ubuntu distro, with Docker Desktop's WSL integration enabled.
The runner then sees a Linux host, which is already a supported platform, and nothing below
under "Native Windows" applies.

1. `wsl --install -d Ubuntu`, then enable Docker Desktop → Settings → Resources → WSL
   integration for that distro.
2. **Clone into the Linux filesystem** (`~/pennybench`), not `/mnt/c/...`. Bind mounts and
   Docker builds across the `/mnt/c` boundary are many times slower and break file modes.
3. Install `uv`, then follow [RUNNER.md](../RUNNER.md#one-time-setup) unchanged
   (`.venv/bin/python` paths are correct in WSL).
4. **Sign in inside WSL.** `claude auth login` in WSL writes `~/.claude/.credentials.json`,
   which the runner reads on any non-macOS host. A login made in Windows or on the Mac is not
   visible there. Do not copy `.credentials.json` between machines through git or chat.
5. Run `pennybench check <experiment>` before the first run, then the `audit` stage.

## Native Windows (PowerShell), if you must

The code now handles the known differences (no `os.uname`, no `killpg`, `.exe` suffixes,
Windows env passthrough, LF-only launcher, `.gitattributes`). It has **not** been run end to
end on Windows. Harbor 0.24 has its own Windows code paths (`docker_windows.py`, `win32`
checks), but those serve Windows-*container* tasks; PennyBench's Linux task images need Docker
in Linux-container mode. Expect to debug the repo's host-side glue, not Harbor itself.

- Python 3.12, `uv venv .venv --python 3.12`, executables are in `.venv\Scripts\`
  (`.venv\Scripts\python.exe -m pip ...`), not `.venv/bin/`.
- Set `PYTHONUTF8=1` (or `setx PYTHONUTF8 1`). Reports and traces are read and written with
  the default encoding, which is cp1252 on Windows and corrupts or rejects non-ASCII text.
- Docker Desktop in **Linux containers** mode (WSL2 backend). Windows containers do not work.
- Git: `git config core.autocrlf false` before cloning, or rely on the repo's
  `.gitattributes`. A CRLF `launcher.sh`, `test.sh`, or Dockerfile fails in the container with
  `exec format error` / `no such file or directory`.
- Long paths: `git config core.longpaths true` and enable Windows long-path support; Harbor
  trial directories and task-dataset paths get deep.
- Credentials come from `%USERPROFILE%\.claude\.credentials.json`. The `chmod 600` is a no-op
  on NTFS, so the file is protected only by your profile's ACL. Keep the profile private.
- The capture proxy binds `127.0.0.1` and containers reach it as `host.docker.internal`,
  which Docker Desktop provides on Windows. The Windows firewall may prompt the first time
  `mitmdump.exe` listens; allow it on private networks only.
- Run trials from a normal terminal, not an IDE-embedded one, so that a timeout's
  `taskkill /T` cleans up Harbor and its `docker compose` children.
- Unsupported on native Windows: the POSIX-only test `test_launcher_uses_container_architecture`
  and `test_real_inherited_pipe_is_released` are skipped. Run them under WSL.

## Linux (non-WSL) hosts

- Same as the WSL path. Docker Engine works; `host.docker.internal` is not defined there by
  default, so the task containers need `--add-host=host.docker.internal:host-gateway`. Confirm
  that Harbor's compose file adds it (or set it via a Docker daemon `extra_hosts` default) and
  that `pennybench check` plus one `audit`-stage trial shows captured traffic.
- Credentials come from `~/.claude/.credentials.json`.

## Architecture: expect different numbers and a different task set

- The Terminal-Bench 2.1 images are mostly x86-only. On the Mac they ran under emulation
  (slow, flaky, some tasks excluded). A native x86-64 PC runs them natively: faster and with
  fewer emulation-induced failures. Results are **not directly comparable** with the Mac run;
  record the host (CPU, RAM, Docker version) with every run and do not mix hosts within one
  paired comparison.
- Conversely, arm64-only images would need emulation on x86. `docker_arch()` in
  `pennybench/agent_cache.py` reads the daemon's architecture, and the agent-binary cache
  fetches both arm64 and x64 builds by default, so mixed datasets still work.
- Give Docker Desktop/WSL enough resources: `%UserProfile%\.wslconfig` with
  `memory=` (at least 16 GB for the full suites), `processors=`, and `swap=`. The default
  50%-of-RAM cap is the most common cause of OOM-killed trials. Task images and the 40 GB
  build cache live in the WSL virtual disk (`docker_data.vhdx`); make sure that drive has
  room, or move the disk in Docker Desktop settings.

## Things that carry over from the Mac and must be redone

| Item | Action |
|---|---|
| `pennybench.local.toml` | Recreate from `config.example.toml`; it is gitignored. Set `[artifacts] store` to a path on the fast Linux/WSL disk. |
| `.env` (tokens, endpoint keys) | Recreate by hand; gitignored on purpose. |
| Claude login | `claude auth login` again on the new host (see above). |
| `runs/` store, dataset cache, agent-binary cache | Do not copy; they re-download and re-verify by pinned hash. Copy `runs/` only if you want old results for `report`. |
| Docker `pennybench` buildx builder | Created automatically by the `[docker] builder` setting. |
| Path scrubbing in exports | The `export_results.py` scripts redact `/home/...` and `C:\Users\...` paths as well as `/Users/...`; still skim an export before publishing. |

## Verify the port

```sh
python -m pytest tests -q          # expect the two POSIX-only tests skipped on native Windows
pennybench check experiments/smoke-route.yaml
pennybench run   experiments/smoke-route.yaml   # one cheap pair; then audit and report
```

A passing `audit` on that smoke run is the real proof that the proxy, the Docker alias, the
login mount and cleanup all work on the new host.
