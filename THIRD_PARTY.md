# Third-party components

PennyBench's own code, documentation and published results are licensed under
Apache-2.0 (see `LICENSE`). The components below keep their own licenses.

| Component | License | How it is used |
| --- | --- | --- |
| [Ponytail](https://github.com/DietrichGebert/ponytail), (c) 2026 DietrichGebert | MIT | Vendored in `arms/ponytail/` at commit `16f2980` (v4.8.4) with its `LICENSE`; see `arms/ponytail/PROVENANCE.md`. |
| [SkillsBench](https://github.com/benchflow-ai/skillsbench) (`benchflow/skillsbench@v1.1`) | Apache-2.0 | Not included. Downloaded by `benchmarks/skillsbench/prepare.py` and pinned by task-tree hash. |
| [Harbor](https://github.com/harbor-framework/harbor) 0.24.0 | Apache-2.0 | Not included. Installed as a dependency. |
| mitmproxy, numpy, scipy, PyYAML | See each project | Not included. Installed as dependencies. |
| Claude Code | Anthropic terms | Not included. Installed into task containers under the user's own account. |

## SkillsBench task skills

Individual task skills inside the dataset have their own terms. Roughly 30 of 232 are
marked proprietary (Anthropic's docx, pdf, pptx and xlsx skills, with `LICENSE.txt`
forbidding copying or redistribution outside Anthropic's services); others are MIT or
reference their upstream licenses. This repository does not redistribute them, and
published results contain derived statistics only. Do not commit downloaded task
directories or raw transcripts.
