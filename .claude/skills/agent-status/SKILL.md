---
name: agent-status
description: Health dashboard for all agents — last-run timestamp, launchd loaded status, recent errors, missed slots. Use when the user asks "agents 状态" / "哪个 agent 漏跑了" / "/agent-status".
disable-model-invocation: true
---

# agent-status

Generate a one-shot health snapshot across every agent in this repo.

## Procedure

1. **Read the canonical agent list** from the root `CLAUDE.md` agents table. Slots are encoded in the "触发" column (e.g., `launchd（morning2/afternoon/night + catchup）`).
2. **Read every stamp** under `.stamps/`. Each file's contents is the date of the last successful run (TZ=Asia/Tokyo). The filename is the slot.
3. **Check launchd state** with `launchctl list 2>/dev/null | grep -E 'com\.(financial_news|brain_science|notes_sync|daily_brief)\.'`. Columns: PID · LastExitStatus · Label. PID `-` means not currently running, which is normal for scheduled jobs.
4. **Tail each agent log** (last 30 lines of `agents/<name>/<name>.log`). Look for:
   - `Traceback`
   - `^\[重试\]`
   - `ERROR|Failed|failed`
   - `exit [1-9]`
   - `429|503|TimeoutError`
5. **Render the table** below.

## Output format

```
## Agent Status — <today JST>

| agent          | slot       | last stamp | launchd | last exit | recent error |
|----------------|------------|------------|---------|-----------|--------------|
| financial_news | morning2   | 2026-05-19 | loaded  | 0         | —            |
| financial_news | afternoon  | 2026-05-18 | loaded  | 0         | —            |
| brain_science  | night      | (missing)  | loaded  | 1         | Groq 429     |
| ...            |            |            |         |           |              |

### Missed slots
- brain_science.morning — stamp missing for today

### Suggested actions
- `rm .stamps/brain_morning && agents/brain_science/run.sh morning`
```

## Constraints

- **Read-only.** Never delete stamps or touch launchd.
- Use Asia/Tokyo dates throughout.
- Agents without launchd plist (paper_reader, shukatsu_youtube) show `launchd: manual`.
- If `.stamps/<slot>` is missing entirely, mark `(missing)` not `(unknown)`.
- For agents with multiple slots, output one row per slot.
