# ClaudeCode — a collection of macOS automation agents

[简体中文](README.md) | **English** | [日本語](README.ja.md)

A set of personal automation agents that run on macOS: they periodically pull news / academic papers / investment-bank commentary, have an LLM organize it, and then **push it to WeChat via [ServerChan](https://sct.ftqq.com/)** or write it into a local [Obsidian](https://obsidian.md/) vault. Scheduling is handled by `launchd`, backed by a lightweight governance layer (scoped secret injection, a path registry, index reconciliation, and a catch-up mechanism).

> This is a real, in-use personal project. The repository contains no secrets or personal data — every private config lives only as a `*.example` template, and the real files are excluded via `.gitignore`.

## Agents

| Agent | Directory | Job | Trigger | Depends on |
|-------|-----------|-----|---------|------------|
| Financial news | `agents/financial_news/` | Push financial news to WeChat 3×/day | launchd (morning/afternoon/night + boot catch-up) | NewsAPI + GNews + Groq + ServerChan |
| Brain science | `agents/brain_science/` | Push sourced brain-science facts morning/night | launchd (catch-up + night) | PubMed + NewsAPI + Groq + ServerChan |
| Wall Street AI takes | `agents/wallstreet_ai/` | AI-investing articles from banks' official channels → themed digest | launchd (Mon/Fri 08:00) | Claude + ServerChan |
| Daily brief | `agents/daily_brief/` | Read recent vault content + today's calendar → connections/patterns/questions | launchd (daily 08:30) | Obsidian + Groq |
| Notes sync | `agents/notes_sync/` | Apple Notes ↔ Obsidian two-way sync | launchd (every 4 h) | Obsidian + Apple Notes |
| Paper reader | `agents/paper_reader/` | Fetch from PubMed/CiNii/PDF → Claude structuring → Obsidian | manual CLI | Claude + Obsidian |

> Obsidian-backed agents need a local vault with its path configured in `vault.paths.env` (see below). The pure-push agents (financial news / brain science / Wall Street) don't require Obsidian.

## Infrastructure highlights

- **Scoped secret injection (keys not prompts):** `.env` is the single source of truth, but each `run.sh` uses `tools/load_env.sh KEY1 KEY2 ...` to inject **only the keys it needs** — an agent process never sees unrelated credentials.
- **Vault path registry:** `vault.paths.env` is the single place where every Obsidian path is defined (router pattern). Python resolves it via `tools/vault_paths.py`, shell scripts `source` it directly, and **no script ever hardcodes a vault path**.
- **index/log reconciliation:** `tools/vault_index_sync.py` reconciles the vault's `index.md` against the actual files; agents that write to the vault call it automatically after running.
- **Catch-up mechanism:** `.stamps/<slot>` prevents duplicate pushes within the same slot; `catchup.sh` reruns slots that were missed while the machine was off, at boot/login.
- **Self-locating scripts:** every `run.sh` resolves the repo root via `$SCRIPT_DIR`, contains no absolute paths, and is clone-and-run across machines/users.

## Quick start

```bash
# 1. Clone
git clone <your-fork-url> ClaudeCode && cd ClaudeCode

# 2. Configure secrets (only the keys the agents you want actually need)
cp .env.example .env
$EDITOR .env

# 3. (Obsidian-backed agents only) configure vault paths
cp vault.paths.example.env vault.paths.env
$EDITOR vault.paths.env

# 4. (paper_reader only) configure research interests
cp agents/paper_reader/research_interests.example.yaml agents/paper_reader/research_interests.yaml

# 5. Install the scheduled jobs into launchd (plist placeholders are rewritten to this machine's real path)
bash scripts/install_launchagents.sh

# 6. Run once to verify (pass the slot name)
agents/financial_news/run.sh morning2
```

The required API keys and where to get them are listed in [.env.example](.env.example). Python defaults to the system framework interpreter; override it with an environment variable: `PYTHON=/path/to/python3 agents/financial_news/run.sh morning2`.

## Repository layout

```
agents/<name>/        # each agent ships its own run.sh / CLAUDE.md / plist
tools/                # load_env.sh / vault_paths.py / vault_index_sync.py
scripts/              # install_launchagents.sh one-shot deploy
.env.example          # secrets template
vault.paths.example.env  # vault paths template
CLAUDE.md             # operating manual for Claude Code (also the best architecture doc)
```

Each agent directory has its own `CLAUDE.md` detailing its data flow, parameters, and caveats.

## Platform requirements

- macOS (depends on `launchd`; notes sync and the calendar section depend on Apple Notes / Calendar and need authorization)
- Python 3.14 (or point the `PYTHON` environment variable at your own interpreter)

## License

[MIT](LICENSE)
