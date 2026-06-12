#!/usr/bin/env ~/.claude/skills/obsidian-second-brain/.venv/bin/python
"""
就活 YouTube ingestion — 字幕を抽出して Obsidian 素材/YouTube/ に保存する。
NotebookLM 連携のため、AI 要約は行わない（字幕原文のみ保存）。

Usage:
    python ingest.py <url_or_id> [industry]
    python ingest.py --batch urls.txt

industry: 商社 | 金融 | 金融失敗 | 全行業 | 全行業失敗 | auto（省略時は auto）
"""

import re
import ssl
import sys
import json
import urllib.request
from datetime import datetime
from pathlib import Path

_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from vault_paths import vault_path

VAULT_YOUTUBE = vault_path("VAULT_SHUKATSU_SOZAI_YT")
VENV_PY = Path.home() / ".claude/skills/obsidian-second-brain/.venv/bin/python"

INDUSTRY_PATTERNS = [
    ("金融失敗", [r"外銀.*落ち", r"落ち.*外銀", r"失敗.*金融", r"落選", r"不合格.*金融"]),
    ("商社",     [r"商社", r"伊藤忠", r"三菱商事", r"三井物産", r"住友商事", r"丸紅", r"双日", r"兼松"]),
    ("金融",     [r"外銀", r"外資金融", r"投資銀行", r"ゴールドマン", r"モルスタ", r"JPモルガン",
                  r"メガバンク", r"三井住友銀行", r"三菱UFJ", r"みずほ", r"証券", r"野村", r"大和"]),
]


def parse_video_id(s: str) -> str:
    s = s.strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", s):
        return s
    for pat in [r"(?:v=|/v/|youtu\.be/|/shorts/|/embed/)([A-Za-z0-9_-]{11})"]:
        m = re.search(pat, s)
        if m:
            return m.group(1)
    raise ValueError(f"YouTube ID を解析できません: {s}")


def classify_industry(title: str) -> str:
    for industry, patterns in INDUSTRY_PATTERNS:
        for pat in patterns:
            if re.search(pat, title):
                return industry
    return "全行業"


def get_youtube_meta(video_id: str) -> tuple[str, str]:
    """YouTube ページから title と channel を取得（API key 不要）。"""
    url = f"https://www.youtube.com/watch?v={video_id}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=10, context=_SSL_CTX) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
        m = re.search(r'"title":"((?:[^"\\]|\\.)*?)","lengthSeconds"', html)
        title = json.loads(f'"{m.group(1)}"') if m else f"Video {video_id}"
        m2 = re.search(r'"ownerChannelName":"((?:[^"\\]|\\.)*?)"', html)
        channel = json.loads(f'"{m2.group(1)}"') if m2 else "(不明)"
        return title, channel
    except Exception as e:
        print(f"  [meta 取得失敗: {e}]")
        return f"Video {video_id}", "(不明)"


def get_transcript(video_id: str) -> str | None:
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        api = YouTubeTranscriptApi()
        fetched = api.fetch(video_id, languages=["ja", "en", "zh-Hans", "zh-Hant"])
        return " ".join(seg.text for seg in fetched.snippets if seg.text).strip()
    except Exception as e:
        print(f"  [字幕取得失敗: {e}]")
        return None


def slugify_title(title: str) -> str:
    """ファイル名に使えない文字を除去して短縮。"""
    title = re.sub(r"[【】「」『』〔〕［］《》〈〉｛｝（）()【】\[\]{}]", "", title)
    title = re.sub(r"[/\\:*?\"<>|]", "", title)
    title = re.sub(r"\s+", "", title)
    return title[:40]


def ingest_video(url_or_id: str, industry_override: str | None = None) -> dict | None:
    try:
        video_id = parse_video_id(url_or_id)
    except ValueError as e:
        print(f"❌ {e}")
        return None

    print(f"→ {video_id} 処理中...", end=" ", flush=True)

    title, channel = get_youtube_meta(video_id)
    transcript = get_transcript(video_id)

    if not transcript:
        print("❌ 字幕なし")
        return None

    industry = industry_override if industry_override and industry_override != "auto" else classify_industry(title)
    today = datetime.now().strftime("%Y-%m-%d")
    slug = slugify_title(title)
    filename = f"{today}_{slug}_{industry}.md"

    frontmatter = (
        f"---\n"
        f"title: {json.dumps(title, ensure_ascii=False)}\n"
        f"source: https://www.youtube.com/watch?v={video_id}\n"
        f"source_type: YouTube\n"
        f"video_id: {video_id}\n"
        f"channel: {json.dumps(channel, ensure_ascii=False)}\n"
        f"industry: {industry}\n"
        f"added: {today}\n"
        f"distilled: false\n"
        f"---\n\n"
    )

    note = (
        frontmatter
        + f"# {title}\n\n"
        + f"**チャンネル:** {channel}\n"
        + f"**URL:** https://www.youtube.com/watch?v={video_id}\n\n"
        + f"## 字幕全文\n\n"
        + transcript
        + "\n"
    )

    out_path = VAULT_YOUTUBE / filename
    out_path.write_text(note, encoding="utf-8")
    print(f"✅ [{industry}] {slug} → {filename}")

    return {
        "video_id": video_id,
        "title": title,
        "channel": channel,
        "industry": industry,
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "file": str(out_path),
    }


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(1)

    results = []

    if args[0] == "--batch" and len(args) >= 2:
        urls = Path(args[1]).read_text().splitlines()
        for line in urls:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            url = parts[0]
            industry = parts[1] if len(parts) > 1 else "auto"
            r = ingest_video(url, industry)
            if r:
                results.append(r)
    else:
        url = args[0]
        industry = args[1] if len(args) > 1 else "auto"
        r = ingest_video(url, industry)
        if r:
            results.append(r)

    if results:
        print(f"\n完了: {len(results)} 件を素材/YouTube/ に保存")
        print("\nNotebookLM に追加すべき URL:")
        for r in results:
            print(f"  [{r['industry']}] {r['url']}")
        # vault 治理：写入后对账 index/log（best-effort，失败不影响 ingest 结果）
        import subprocess
        subprocess.run(
            [sys.executable,
             str(Path(__file__).resolve().parents[2] / "tools" / "vault_index_sync.py"),
             "--fix", "--reason", "shukatsu_youtube"],
            check=False,
        )


if __name__ == "__main__":
    main()
