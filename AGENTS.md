# AGENTS.md

Working conventions for agents on this repository.

## Approach

- Read existing files before writing. Don't re-read unless changed.
- Thorough in reasoning, concise in output.
- Skip files over 100KB unless required.
- No sycophantic openers or closing fluff.
- No emojis or em-dashes.
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
