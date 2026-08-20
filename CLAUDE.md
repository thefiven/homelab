# CLAUDE.md

Working conventions for agents on this repository.

## Approach

- Read existing files before writing. Don't re-read within the same turn
  unless something else (a hook, another agent, a git operation) may have
  changed it since.
- Thorough in reasoning, concise in output.
- Skip files over 100KB unless the task needs their content directly: a
  citation, a conflict check, a direct question about that file.
- No sycophantic openers or closing fluff.
- No emojis or em-dashes in new prose. Existing docs that already use them
  (the research notes, ADR-0001, ADR-0002) are not retrofitted.
- Do not guess APIs, versions, flags, commit SHAs, or package names. Verify by reading code or docs before asserting.

## Language

Everything in this repository is written in English: code, configuration,
labels, branch names, commit messages, pull requests, issues, ADRs and
documentation. Conversations with the maintainer happen in French — the
repository is the artefact, not the conversation.

## Agent skills

### Issue tracker

Issues live in the GitHub Issues of `thefiven/homelab`, driven with `gh`.
See `docs/agents/issue-tracker.md`.

### Triage labels

The canonical vocabulary is kept as-is — `needs-triage`, `needs-info`,
`ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `CONTEXT.md` at the root, ADRs under `docs/adr/`.
See `docs/agents/domain.md`.

After `/wizard` regenerates a wizard script, replace its inlined library
section with `source "$(dirname "${BASH_SOURCE[0]}")/lib/wizard.sh"` before
committing. Wizard-generated scripts stay Bash even as other scripts convert
to Python (see below) - the `/wizard` skill's generator only produces Bash,
and converting its output without converting the generator would just drift
the two apart.

### Python scripts

`scripts/` is Bash by default, converted to Python one script at a time,
each conversion its own ticket opened when that script is next touched (no
bulk rewrite). Conventions for those conversions:

- Standard-library-first; add a third-party dependency only when a specific
  script genuinely needs one.
- Light type hints, no mypy enforcement.
- Keep the `--self-check` CLI convention these scripts already use instead
  of introducing a test framework.
- Bare `#!/usr/bin/env python3` shebang - no PEP 723 inline metadata or uv
  until a script actually needs a dependency.
- `.py` naming for converted scripts.

black, isort, and flake8 run on `scripts/*.py` in the same pre-commit/CI
gate as shellcheck (`pyproject.toml`, `.flake8`).
