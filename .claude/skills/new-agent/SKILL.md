---
name: new-agent
description: Scaffold a new agent under agents/<name>/ following this repo's run.sh + (launchd | CLI) pattern. Use when the user says "新加一个 agent" or "/new-agent <name>".
disable-model-invocation: true
---

# new-agent

Scaffold a new agent directory matching this repo's conventions.

## Usage

```
/new-agent <name> [--type=scheduled|cli]
```

- `scheduled` (default): launchd-driven with `.stamps/<slot>` dedupe and one-shot retry. Pattern from `agents/financial_news/`.
- `cli`: manual CLI invocation, run.sh passes `"$@"` through. Pattern from `agents/paper_reader/`.

## Procedure

1. **Validate** `<name>` is snake_case and `agents/<name>/` does not exist. If exists, abort with error.
2. **Resolve `--type`** (default `scheduled`).
3. **Create** `agents/<name>/` and inside it:
   - `CLAUDE.md` — agent-local instructions. Use template `templates/agent.CLAUDE.md`, replace `<NAME>` with `<name>`.
   - `requirements.txt` — empty by default; add deps if user specified them in the request.
   - `<name>.py` — main script from `templates/skeleton.py`, replace `<NAME>` token.
   - `run.sh` — copy from `templates/scheduled.run.sh` or `templates/cli.run.sh`, replace `<NAME>` and `<AGENT_DIR>`. Then `chmod +x`.
4. **For `scheduled` only**: emit (do NOT write) a `~/Library/LaunchAgents/com.<name>.<slot>.plist` template snippet inline in the chat. Ask the user for the slot name and schedule first; do not pre-fill. Tell the user the reload commands after they write the plist.
5. **Update root `CLAUDE.md`** agents table — append a new row. Use the same column structure as existing rows.
6. **Do NOT auto-load any launchd job** — that's the user's call.

## Conventions to respect

- Python interpreter: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3`
- All `run.sh` start with:
  ```bash
  set -a
  source /Users/jiayi/Developer/ClaudeCode/.env
  set +a
  ```
- Logs: `agents/<name>/<name>.log`. `run.sh` is responsible for tail-truncating to 500 lines (scheduled template does this).
- Stamps: `.stamps/<slot>` at repo root (NOT `~/.stamps/`).
- Scheduled `run.sh` first arg is the slot name, written to `.stamps/` only on success.
- CLI `run.sh` takes no slot — pure passthrough.

## Templates

See `.claude/skills/new-agent/templates/`:
- `scheduled.run.sh`
- `cli.run.sh`
- `skeleton.py`
- `agent.CLAUDE.md`

After scaffolding, print the next steps to the user:
1. Fill in business logic in `<name>.py`
2. Add dependencies to `requirements.txt`
3. (scheduled) Write the plist, then `launchctl load`
4. (scheduled) Test manually: `agents/<name>/run.sh <slot>`
