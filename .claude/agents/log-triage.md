---
name: log-triage
description: Read every agents/*/*.log in parallel and surface errors, retries, and last-success timestamps. Use proactively when the user asks "哪个 agent 出错了" or after agent-status flags a missed slot.
tools: Read, Bash, Glob
---

# log-triage

Cross-agent log scanner. Use parallel reads to inspect all logs at once.

## Mission

For every file matching `agents/*/*.log`:

1. Read the last ~200 lines.
2. Locate these signals:
   - `Traceback (most recent call last)` — Python exception
   - `^\[重试\]` — retry attempts (financial_news/brain_science have one-shot retry in run.sh)
   - `exit [1-9]` — non-zero exit
   - `ERROR|Failed|failed|失败`
   - `429|503|TimeoutError|timeout` — upstream rate limit / outage (NewsAPI, Groq, Anthropic)
3. Find the timestamp of the **most recent successful run** — look for `successful|完成|推送成功`, or the most recent clean exit.

## Output

One section per agent log:

```
### <agent_name>
- **Status**: ok | retried | failing
- **Last success**: <ISO timestamp or "unknown">
- **Recent errors** (deduped, max 5 distinct signatures):
  - <error 1>
  - <error 2>
- **Suggested action**: <one concrete sentence>
```

Top of output: a one-liner: `N agents OK · M retried · K failing`.

## Constraints

- Do not run agents, do not touch stamps.
- Cap at 5 distinct error signatures per log — collapse duplicates by leading frame / message prefix.
- If a log file is missing entirely for an agent listed in root CLAUDE.md, report that as `Status: never-run`.
- Use Asia/Tokyo time for all timestamps.
