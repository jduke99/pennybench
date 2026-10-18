# ponytail, vendored for the PennyBench calibration run

Source: https://github.com/DietrichGebert/ponytail at commit `16f2980` (v4.8.4, MIT, see
`LICENSE`), the version JetBrains tested.

- `ruleset.txt` is the text ponytail's own `hooks/ponytail-instructions.js` returns for the
  default mode (`full`), generated with
  `node -e "process.stdout.write(require('./hooks/ponytail-instructions.js').getPonytailInstructions(require('./hooks/ponytail-config.js').DEFAULT_MODE))"`.
  sha256 `da4fb09cff2f6726691ce6591cebc38c95597d79da132e49c6fa2665c4e8a3ff`.
- `skills/ponytail/` is that commit's `skills/ponytail/` directory, unchanged.

The treatment arm installs the skill and appends the ruleset after the task instruction, as in
JetBrains' setup. Like theirs, it does not reproduce the plugin's first-run statusline nudge or
its subagent re-injection.
