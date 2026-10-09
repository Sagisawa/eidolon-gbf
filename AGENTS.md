## Agent skills

### Issue tracker

Issues live as local markdown files under `.scratch/<feature>/`. See `docs/agents/issue-tracker.md`.

### Triage labels

Default vocabulary: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `GLOSSARY.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.

### Frontend

前端用 shadcn/ui（底层 Base UI，样式 `base-nova`）加 Tailwind v4。写前端代码前读 `frontend/AGENTS.md` 的「shadcn 纪律」，视觉规范以 `DESIGN.md` 为准。
