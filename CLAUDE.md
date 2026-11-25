# horror-pipeline — Claude Code notes

Indonesian serialized horror pipeline (channel Kemenyan Malam). Full workflow: `SKILL.md` + `references/00-11`.

## Model routing
Default model for this project is **Sonnet** (`.claude/settings.json`). Delegate to the project subagents:

| Task | Subagent | Model |
|------|----------|-------|
| Write/rewrite script.yaml, styles.yaml, part structure (references/01) | `story-writer` | opus |
| Design a new pipeline feature; debug a hard multi-file bug → plan only | `pipeline-architect` | opus |
| Implement planned changes, small fixes, config edits, commits/pushes | `pipeline-dev` | sonnet |
| check / import-flow / sound-import / tts / build / review, review reports & contact sheets, technical fixes, titles/descriptions/captions | `producer` | sonnet |
| Watch a long render or TTS retry; report only when finished/failed (read-only) | `render-watcher` | haiku |

Rules:
- Escalate to Opus **only** for story writing, architecture, or a bug Sonnet failed to fix after 2 attempts
  (then `pipeline-architect` plans, `pipeline-dev` implements).
- Never use Opus just to run commands or to wait for renders; waiting = `render-watcher`.
- Keep replies to the user short: what was done, file paths, what they need to do.

## House rules
- **Never print `.env` or API keys** (Gemini keys live only in `.env`; logs already mask them).
- **One heavy render at a time** (no two `build`s, no build + TTS batch in parallel).
- **Never kill a running ffmpeg/render** (Ctrl+C, kill, stopping its terminal) — it breaks the render; wait.
- Media is not on `main` (.gitignore); assets live on branch `muse-assets` (references/00). Never `git add -f`
  media to main; push assets with `scripts/push_assets.py`.
- Don't overwrite user images (`import-flow --force` only when asked); don't change approved visual style
  (outro, vertical subtitles, part covers) unless asked.
- Numbers reported to the user (durations, wpm, LUFS, sizes, render time) come from command output or ffprobe.
