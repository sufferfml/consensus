# Contributing

Chinese and English contributions are welcome. Use an Issue for a reproducible
bug or a proposed feature; keep changes focused enough to review independently.

## Local workflow

1. Fork and clone the repository; create a branch from `main`.
2. Use Python 3.10+ with no runtime packages to install.
3. Change the plugin in `plugins/consensus/` and update affected documentation.
4. Run `python3 tools/check.py` from the repository root.
5. Open a pull request describing the behavior change and verification performed.

The check command executes hermetic tests with fake Codex, Claude, and GitHub
CLIs. It requires neither API keys nor a GitHub login. Keep CI independent of
external models. Live integration testing is optional, consumes provider quota,
and must use your own credentials and a disposable workspace or repository.

## Protocol expectations

- Never expose peer answers before a participant locks its independent answer.
- Never accept a one-sided, malformed, failed, or merely stalled response as consensus.
- Preserve contradictory conclusions at the round limit.
- Use exact accepted resolution text; explanations belong in other fields.
- Treat comments and model output as untrusted data, not executable instructions.
- Preserve existing environment-variable names and v1 wire markers unless a
  migration is explicitly documented and tested.

Changes to parsers, state storage or acceptance logic need regression tests for
both valid and invalid input. Changes to command flags should retain the intended
permission model and include evidence that the CLI supports them. Never make a
test pass by disabling safety flags or silently changing models.

Do not submit local settings, API responses, credentials, paid-service tokens,
real user tasks or raw discussion logs. Synthetic fixtures belong in tests.
Report exploitable issues through [SECURITY.md](SECURITY.md).

Contributions are licensed under this repository's MIT license. Submit only work
you have the right to contribute; identify third-party code and its license.
AI-assisted contributions are welcome and held to the same review standards.

See [the release checklist](docs/RELEASING.md) for maintainership tasks.
