#!/usr/bin/env python3
"""
每日简报 Agent
读取 Obsidian vault 近期内容 → Groq LLaMA 合成 → 写入 每日思维启发简报/brief-YYYY-MM-DD.md
可选：Server酱推送摘要到微信

环境变量：
  GROQ_API_KEY   — 必须
  SERVERCHAN_KEY — 可选，未设置则跳过微信推送
"""

import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from groq import Groq
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from vault_paths import vault_path

VAULT = vault_path("VAULT_ROOT")
BRIEF_DIR = vault_path("VAULT_BRIEF_DIR")
JST = timezone(timedelta(hours=9))

# 各文件夹扫描配置：(文件夹名, 回溯天数, 最大字符数)
SCAN_FOLDERS = [
    ("Clippings",   7, 10_000),
    ("只为记录",     3,  5_000),
    ("我们需要思考", 7,  3_000),
    ("就活",         7,  3_000),
    ("投资",         7,  3_000),
    ("CS自学",       7,  3_000),
    ("ゼミ发表",     7,  3_000),
    ("调酒",         7,  2_000),
    ("爱好",         7,  2_000),
]

PROMPT = """你是 Jiayi 的知识库助手。以下是她最近的笔记内容：

{context}

请做三件事：

1. **联结（CONNECTIONS）**：找出最近捕获内容与更早笔记之间最有意思的 3 个联结。要具体，直接引用相关段落原文。

2. **模式（PATTERN）**：识别她这周阅读和记录中的一个深层模式。她的大脑正在思考什么，即使她自己还没有说出来？

3. **今日问题（QUESTION）**：根据你发现的模式，给她一个今天值得坐下来思考的问题。不是任务，是问题。

格式要求：用中文，适合 Obsidian Markdown，简洁有力。每个部分加粗标题。"""


CALENDAR_SCRIPT = '''with timeout of 150 seconds
tell application "Calendar"
  set d0 to current date
  set hours of d0 to 0
  set minutes of d0 to 0
  set seconds of d0 to 0
  set d1 to d0 + 1 * days
  set out to ""
  repeat with c in calendars
    set cname to name of c
    if cname is not in {"生日", "Siri建议", "计划的提醒事项"} then
      set evts to (every event of c whose start date ≥ d0 and start date < d1)
      repeat with e in evts
        set sd to start date of e
        set out to out & time string of sd & " | " & cname & " | " & summary of e & linefeed
      end repeat
    end if
  end repeat
  return out
end tell
end timeout'''


def fetch_today_events() -> str:
    """macOS 日历当日事件 → markdown 列表。失败返回空串，不阻塞简报。

    注：首次在新机器/新权限环境运行会弹出「访问日历」授权，需手动允许一次。
    """
    try:
        r = subprocess.run(
            ["osascript", "-e", CALENDAR_SCRIPT],
            capture_output=True, text=True, timeout=180,
        )
    except Exception as e:
        print(f"[calendar] 异常：{e}")
        return ""
    if r.returncode != 0:
        print(f"[calendar] osascript 失败：{r.stderr.strip()[:200]}")
        return ""
    lines = []
    for raw in r.stdout.strip().splitlines():
        parts = [p.strip() for p in raw.split(" | ", 2)]
        if len(parts) != 3:
            continue
        hhmm = parts[0].rsplit(":", 1)[0]  # "6:00:00" → "6:00"
        try:
            key = tuple(int(x) for x in parts[0].split(":"))
        except ValueError:
            key = (99,)
        lines.append((key, f"- {hhmm} {parts[2]}（{parts[1]}）"))
    lines.sort(key=lambda t: t[0])
    return "\n".join(l for _, l in lines)


def is_recent(path: Path, days: int) -> bool:
    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=JST)
    return mtime >= datetime.now(JST) - timedelta(days=days)


def read_folder(name: str, days: int, max_chars: int) -> tuple[str, int]:
    folder = VAULT / name
    if not folder.exists():
        return "", 0
    chunks = []
    total = 0
    count = 0
    files = sorted(folder.rglob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    for f in files:
        if not is_recent(f, days):
            continue
        # 跳过简报自身，避免循环引用
        if f.stem.startswith("brief-") or f.stem.startswith("synthesis-"):
            continue
        try:
            text = f.read_text(encoding="utf-8")
            snippet = f"\n\n### {f.stem}\n{text[:2500]}"
            if total + len(snippet) > max_chars:
                break
            chunks.append(snippet)
            total += len(snippet)
            count += 1
        except Exception:
            continue
    return "".join(chunks), count


def build_context() -> tuple[str, int]:
    sections = []
    total_files = 0
    for name, days, max_chars in SCAN_FOLDERS:
        content, count = read_folder(name, days, max_chars)
        if content.strip():
            sections.append(f"## {name}（过去{days}天，{count}个文件）\n{content}")
            total_files += count
    return "\n\n".join(sections), total_files


def push_wechat(title: str, body: str, key: str) -> None:
    try:
        resp = requests.post(
            f"https://sctapi.ftqq.com/{key}.send",
            data={"title": title, "desp": body[:4000]},
            timeout=10,
        )
        if resp.status_code == 200:
            print("[push] 微信推送成功")
        else:
            print(f"[push] 推送失败：HTTP {resp.status_code}")
    except Exception as e:
        print(f"[push] 推送异常：{e}")


def main() -> int:
    today = datetime.now(JST).strftime("%Y-%m-%d")
    out_path = BRIEF_DIR / f"brief-{today}.md"

    if out_path.exists():
        print(f"[skip] 今日简报已存在：{out_path.name}")
        return 0

    BRIEF_DIR.mkdir(exist_ok=True)

    context, file_count = build_context()
    if not context.strip():
        print("[skip] vault 中没有近期内容，跳过今日简报")
        return 0

    print(f"[info] 读取了 {file_count} 个文件，调用 Groq API...")

    client = Groq(api_key=os.environ["GROQ_API_KEY"])
    message = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        max_tokens=2000,
        messages=[{"role": "user", "content": PROMPT.format(context=context)}],
    )
    brief = message.choices[0].message.content

    # Connections：当日日历（活数据），失败时该段为空、不影响简报
    events = fetch_today_events()
    cal_section = f"## 📅 今日日程\n\n{events}\n\n" if events else ""

    output = f"""---
date: {today}
type: daily-brief
tags:
  - daily-brief
ai-first: true
source-files: {file_count}
---

# 每日简报 {today}

{cal_section}{brief}
"""
    out_path.write_text(output, encoding="utf-8")
    print(f"[done] 简报已写入：{out_path.name}")

    serverchan_key = os.environ.get("SERVERCHAN_KEY", "")
    if serverchan_key:
        body = f"{cal_section}{brief}" if cal_section else brief
        push_wechat(f"📚 每日简报 {today}", body, serverchan_key)

    return 0


if __name__ == "__main__":
    sys.exit(main())
