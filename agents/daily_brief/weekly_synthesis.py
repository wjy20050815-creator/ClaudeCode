#!/usr/bin/env python3
"""
每周合成（手动触发）
读取 Obsidian vault 过去 7 天内容 → Groq LLaMA → 写入 Inbox/synthesis-YYYY-MM-DD.md

用法：
  python3 weekly_synthesis.py
  python3 weekly_synthesis.py --days 14   # 回溯 14 天
"""

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from groq import Groq

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from vault_paths import vault_path

VAULT = vault_path("VAULT_ROOT")
INBOX = vault_path("VAULT_INBOX")
JST = timezone(timedelta(hours=9))

SCAN_FOLDERS = [
    ("Inbox",       1,  8_000),
    ("Clippings",   7, 10_000),
    ("只为记录",     7,  6_000),
    ("我们需要思考", 7,  4_000),
    ("就活",         7,  4_000),
    ("投资",         7,  3_000),
    ("语言学",       7,  3_000),
    ("CS自学",       7,  3_000),
    ("ゼミ发表",     7,  3_000),
    ("调酒",         7,  2_000),
    ("爱好",         7,  2_000),
]


def is_recent(path: Path, days: int) -> bool:
    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=JST)
    return mtime >= datetime.now(JST) - timedelta(days=days)


def read_folder(name: str, days: int, max_chars: int) -> str:
    folder = VAULT / name
    if not folder.exists():
        return ""
    chunks = []
    total = 0
    files = sorted(folder.rglob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    for f in files:
        if not is_recent(f, days):
            continue
        try:
            text = f.read_text(encoding="utf-8")
            snippet = f"\n\n### {f.stem}\n{text[:3000]}"
            if total + len(snippet) > max_chars:
                break
            chunks.append(snippet)
            total += len(snippet)
        except Exception:
            continue
    return "".join(chunks)


def build_context(days_override: int | None = None) -> str:
    sections = []
    for name, days, max_chars in SCAN_FOLDERS:
        d = days_override if days_override and name != "Inbox" else days
        content = read_folder(name, d, max_chars)
        if content.strip():
            sections.append(f"## {name}（过去{d}天）\n{content}")
    return "\n\n".join(sections)


PROMPT = """你正在阅读 Jiayi 的 Obsidian 知识库。以下是她过去一周的全部笔记内容：

{context}

请做四件事：

1. **浮现中的论点（EMERGING THESIS）**：她正在向哪个想法或立场靠近，即使她自己还没有明说？这个观点是什么？

2. **矛盾（CONTRADICTIONS）**：她最近保存的内容中，有什么与她之前相信的事情相矛盾？从她自己的笔记两边各引用原文。

3. **知识盲区（KNOWLEDGE GAPS）**：根据她正在读和思考的内容，她明显没有在读什么？缺少哪个视角？

4. **一个行动（ONE ACTION）**：综合这个vault里的所有内容，她这周最高杠杆的一件事或一个思考方向是什么？

要直接。挑战她。不要总结她已经知道的东西。用中文。"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=None, help="回溯天数（默认各文件夹独立设置）")
    parser.add_argument("--dry-run", action="store_true", help="只打印 prompt，不调用 API")
    args = parser.parse_args()

    today = datetime.now(JST).strftime("%Y-%m-%d")
    out_path = INBOX / f"synthesis-{today}.md"

    context = build_context(args.days)
    if not context.strip():
        print("[skip] vault 中没有近期内容")
        return 0

    prompt = PROMPT.format(context=context)

    if args.dry_run:
        print(prompt[:2000])
        print(f"\n[dry-run] 输出将写入：{out_path}")
        return 0

    print(f"[info] 正在调用 Claude API 进行每周合成...")
    client = Groq(api_key=os.environ["GROQ_API_KEY"])
    message = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        max_tokens=3000,
        messages=[{"role": "user", "content": prompt}],
    )
    synthesis = message.choices[0].message.content

    INBOX.mkdir(exist_ok=True)
    output = f"""---
date: {today}
type: weekly-synthesis
tags:
  - weekly-synthesis
ai-first: true
---

# 每周合成 {today}

{synthesis}
"""
    out_path.write_text(output, encoding="utf-8")
    print(f"[done] 每周合成已写入：{out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
