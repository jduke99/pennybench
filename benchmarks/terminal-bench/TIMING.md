# Task timing budgets

These are published timeout budgets from the pinned Terminal-Bench 2.1 task files,
not expected durations. Setup/image downloads and package inventory collection add
time. An A/B pair runs the task twice; repetitions multiply that work again.

Source: [pinned upstream task files](https://github.com/harbor-framework/terminal-bench-2-1/tree/7131e4375048a0e408a8fb404b5f499d726b695b/tasks).

The agent budgets are: 48 tasks at 15 minutes; 17 at 30; 13 at 60; five at 20;
two at 40; one each at 10, 12.5, 120, and 200 minutes. The median is 15 minutes.
The separate verifier budget is often as large as the agent budget, but ordinary
successful verifications may finish much sooner.

Initial local reference-solution timings on 2026-10-19, including Harbor setup and
verification but excluding subsequent package inventory/cache housekeeping:

| Task | Measured elapsed time | Reward |
| --- | ---: | ---: |
| adaptive-rejection-sampler | 84 seconds | 1.0 |
| bn-fit-modify | 130 seconds | 1.0 |

These execute supplied solutions, so they do not predict how long Claude Code
will need to solve the tasks. Most images run under x86 emulation on this Mac.
Model-run estimates should be updated as the first selected pairs complete.

The selected first study uses 72 tasks (144 trials), with agent/verifier limits
at most 30 minutes each and RAM at most 8 GB per task. Its schedule sorts by agent
timeout, then verifier timeout, retaining a seeded shuffle for ties and alternating
arm order within adjacent pairs. These are time limits, not expected runtimes.

For scheduling scenarios only, 89 tasks × two arms × one repetition is 178 trials:
5 minutes per trial means about 15 hours; 10 means about 30 hours; 20 means about
59 hours. Add setup/verifier time if the assumed duration covers only agent work,
and allow for subscription usage-window pauses. These are arithmetic scenarios,
not measured forecasts.

| Task | Agent limit (minutes) | Verifier limit (minutes) |
| --- | ---: | ---: |
| adaptive-rejection-sampler | 15 | 15 |
| bn-fit-modify | 60 | 60 |
| break-filter-js-from-html | 20 | 20 |
| build-cython-ext | 15 | 15 |
| build-pmars | 15 | 15 |
| build-pov-ray | 200 | 200 |
| caffe-cifar-10 | 60 | 20 |
| cancel-async-tasks | 15 | 15 |
| chess-best-move | 15 | 15 |
| circuit-fibsqrt | 60 | 60 |
| cobol-modernization | 15 | 15 |
| code-from-image | 20 | 20 |
| compile-compcert | 40 | 40 |
| configure-git-webserver | 15 | 15 |
| constraints-scheduling | 20 | 20 |
| count-dataset-tokens | 15 | 15 |
| crack-7z-hash | 30 | 15 |
| custom-memory-heap-crash | 30 | 30 |
| db-wal-recovery | 15 | 15 |
| distribution-search | 60 | 60 |
| dna-assembly | 30 | 30 |
| dna-insert | 30 | 30 |
| extract-elf | 15 | 15 |
| extract-moves-from-video | 30 | 30 |
| feal-differential-cryptanalysis | 30 | 30 |
| feal-linear-cryptanalysis | 30 | 30 |
| filter-js-from-html | 30 | 30 |
| financial-document-processor | 20 | 20 |
| fix-code-vulnerability | 15 | 15 |
| fix-git | 15 | 15 |
| fix-ocaml-gc | 60 | 60 |
| gcode-to-text | 15 | 15 |
| git-leak-recovery | 15 | 15 |
| git-multibranch | 15 | 15 |
| gpt2-codegolf | 15 | 15 |
| headless-terminal | 15 | 15 |
| hf-model-inference | 15 | 15 |
| install-windows-3.11 | 60 | 60 |
| kv-store-grpc | 15 | 15 |
| large-scale-text-editing | 20 | 20 |
| largest-eigenval | 15 | 15 |
| llm-inference-batching-scheduler | 30 | 30 |
| log-summary-date-ranges | 15 | 15 |
| mailman | 30 | 30 |
| make-doom-for-mips | 15 | 15 |
| make-mips-interpreter | 30 | 30 |
| mcmc-sampling-stan | 30 | 30 |
| merge-diff-arc-agi-task | 15 | 15 |
| model-extraction-relu-logits | 15 | 15 |
| modernize-scientific-stack | 10 | 10 |
| mteb-leaderboard | 60 | 60 |
| mteb-retrieve | 30 | 30 |
| multi-source-data-merger | 15 | 15 |
| nginx-request-logging | 15 | 15 |
| openssl-selfsigned-cert | 15 | 15 |
| overfull-hbox | 12.5 | 6 |
| password-recovery | 15 | 15 |
| path-tracing | 30 | 30 |
| path-tracing-reverse | 30 | 30 |
| polyglot-c-py | 15 | 15 |
| polyglot-rust-c | 15 | 15 |
| portfolio-optimization | 60 | 60 |
| protein-assembly | 30 | 30 |
| prove-plus-comm | 15 | 15 |
| pypi-server | 15 | 15 |
| pytorch-model-cli | 15 | 15 |
| pytorch-model-recovery | 15 | 15 |
| qemu-alpine-ssh | 15 | 15 |
| qemu-startup | 15 | 15 |
| query-optimize | 15 | 30 |
| raman-fitting | 15 | 15 |
| regex-chess | 60 | 60 |
| regex-log | 15 | 15 |
| reshard-c4-data | 60 | 60 |
| rstan-to-pystan | 30 | 30 |
| sam-cell-seg | 120 | 120 |
| sanitize-git-repo | 15 | 15 |
| schemelike-metacircular-eval | 40 | 40 |
| sparql-university | 15 | 15 |
| sqlite-db-truncate | 15 | 15 |
| sqlite-with-gcov | 15 | 15 |
| torch-pipeline-parallelism | 15 | 15 |
| torch-tensor-parallelism | 15 | 15 |
| train-fasttext | 60 | 60 |
| tune-mjcf | 15 | 15 |
| video-processing | 60 | 60 |
| vulnerable-secret | 15 | 15 |
| winning-avg-corewars | 60 | 60 |
| write-compressor | 15 | 15 |
