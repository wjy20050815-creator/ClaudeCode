#!/usr/bin/env python3
"""
华尔街 AI 投资观点播报 Agent

各大投行/独立研究机构【官方公开栏目】→ Google News site定向 RSS
→ 解码真实 URL → Jina 抓正文全文 → Claude 主题深读（中英混合）→ Server酱微信推送

只抓官方域名内的文章（site: 限定符），不含媒体二手报道与付费墙研报。

环境变量：
  ANTHROPIC_API_KEY  — Claude API 密钥（必须，console.anthropic.com）
  SERVERCHAN_KEY     — Server酱 SendKey（可选，未设置则只打印）
"""

import argparse
import html
import json
import os
import re
import sys
import time
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import quote
from xml.etree import ElementTree as ET

import anthropic
import pytz
import requests

# ── 机构清单（官方域名）──────────────────────────────────────────────────────
# (显示名, 官方域名)。顶级投行全覆盖 + 独立研究机构。
# 注意：独立研究机构（Wedbush/Bernstein）很少有公开栏目，site定向下覆盖可能稀疏，
#       这是「只要官方栏目」决策的预期结果。
INSTITUTIONS = [
    ("Goldman Sachs",   ["goldmansachs.com"]),
    ("Morgan Stanley",  ["morganstanley.com"]),
    ("JPMorgan",        ["jpmorgan.com"]),                       # 含 am./privatebank. 子域
    ("BofA",            ["bofa.com", "bankofamerica.com"]),
    ("Citi",            ["citigroup.com", "citi.com"]),
    ("Wells Fargo",     ["wellsfargo.com"]),
    ("UBS",             ["ubs.com"]),
    ("Barclays",        ["barclays.com", "ib.barclays"]),
    ("Deutsche Bank",   ["db.com"]),
    ("Jefferies",       ["jefferies.com"]),
    ("Wedbush",         ["wedbush.com"]),
    ("Bernstein",       ["bernsteinresearch.com"]),
]

# AI 投资相关关键词（用于 Google 查询 + 二次相关性过滤）
AI_QUERY = '(AI OR "artificial intelligence" OR semiconductor OR "data center" OR Nvidia OR "machine learning")'
AI_TOKENS = [
    "ai", "artificial intelligence", "semiconductor", "chip", "nvidia",
    "data center", "datacenter", "gpu", "machine learning", "genai",
    "generative", "compute", "hyperscaler", "capex", "llm", "openai",
]
# 词边界匹配，避免 "ai" 命中 "Mumbai"/"available" 等子串
AI_TOKEN_RE = re.compile(
    r"\b(" + "|".join(re.escape(t) for t in AI_TOKENS) + r")\b", re.IGNORECASE
)

# 导航/招聘/非文章页停用词（命中即丢弃）
NAV_STOPWORDS = [
    "careers", "career", "students", "internship", "login", "sign in",
    "contact us", "privacy", "our people", "newsroom home", "site map",
    "investor relations", "press release archive",
    # 招聘启事（各行 careers 域会泄漏，常含 AI 关键词）
    "job id", "req id", "apply now", "hiring", "full-time", "full time",
    "architect", "engineering lead", "language engineering", "assistant manager",
]

LOOKBACK_DAYS = 21         # 抓取窗口（拉宽提量；history 去重保证不重复推送）
MAX_ARTICLES = 14          # 送入 LLM 的文章上限
MAX_BODY_CHARS = 5500      # 每篇正文喂给 LLM 的字符上限（Claude 可吃大上下文）
HISTORY_KEEP = 400         # history.txt 保留的已推送条目数
CLAUDE_MODEL = "claude-sonnet-4-6"   # 深读引擎；如需更强可改 claude-opus-4-8
CLAUDE_MAX_TOKENS = 8000   # 输出上限（篇数变多，给足展开空间）

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15"}

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
HISTORY_FILE = os.path.join(SCRIPT_DIR, "history.txt")

JST = pytz.timezone("Asia/Tokyo")
WEEKDAY_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


# ── 抓取：Google News site定向 RSS ───────────────────────────────────────────
def build_feed_url(domains: list) -> str:
    if len(domains) == 1:
        site_clause = f"site:{domains[0]}"
    else:
        site_clause = "(" + " OR ".join(f"site:{d}" for d in domains) + ")"
    query = f"{site_clause} {AI_QUERY}"
    return (
        "https://news.google.com/rss/search?q="
        + quote(query)
        + "&hl=en-US&gl=US&ceid=US:en"
    )


def clean_title(raw: str, source_name: str) -> str:
    """去掉 Google News 标题尾部的 ' - 来源名' 后缀。"""
    t = html.unescape(raw or "").strip()
    # Google 形如 "Article Title - Goldman Sachs"
    if source_name and t.endswith(f" - {source_name}"):
        t = t[: -len(f" - {source_name}")].strip()
    else:
        # 退化：去掉最后一个 ' - xxx' 段
        idx = t.rfind(" - ")
        if idx > 20:
            t = t[:idx].strip()
    return t


def is_relevant(title: str, summary: str) -> bool:
    text = f"{title} {summary}".lower()
    if any(sw in text for sw in NAV_STOPWORDS):
        return False
    if len(title) < 20:                      # 过短多为导航/品牌页
        return False
    return bool(AI_TOKEN_RE.search(text))


def fetch_institution(inst_name: str, domains: list, cutoff_dt: datetime,
                      seen_links: set, seen_titles: set) -> list:
    url = build_feed_url(domains)
    try:
        resp = requests.get(
            url, timeout=15,
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"},
        )
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
    except Exception as e:
        print(f"[{inst_name}] 抓取失败：{e}", file=sys.stderr)
        return []

    out = []
    for item in root.iter("item"):
        link = (item.findtext("link") or "").strip()
        if not link or link in seen_links:
            continue

        src_el = item.find("source")
        src_name = (src_el.text.strip() if src_el is not None and src_el.text else inst_name)

        title = clean_title(item.findtext("title") or "", src_name)
        desc = html.unescape(item.findtext("description") or "")
        desc = re.sub(r"<[^>]+>", " ", desc)          # 去 HTML 标签
        desc = re.sub(r"\s+", " ", desc).strip()[:300]

        pub_raw = item.findtext("pubDate")
        if pub_raw:
            try:
                pub_dt = parsedate_to_datetime(pub_raw)
                if pub_dt.tzinfo is None:
                    pub_dt = pub_dt.replace(tzinfo=timezone.utc)
                if pub_dt < cutoff_dt:
                    continue
            except (TypeError, ValueError):
                pass

        if not is_relevant(title, desc):
            continue

        title_key = re.sub(r"\s+", " ", title.lower()).strip()
        if title_key in seen_titles:         # 同篇文章不同 Google 链接
            continue
        seen_titles.add(title_key)

        seen_links.add(link)
        out.append({
            "inst":    inst_name,
            "source":  src_name,
            "title":   title,
            "summary": desc,
            "url":     link,
        })
    return out


# ── 已推送历史去重 ───────────────────────────────────────────────────────────
def load_history() -> set:
    if not os.path.exists(HISTORY_FILE):
        return set()
    try:
        with open(HISTORY_FILE, encoding="utf-8") as f:
            return {ln.strip() for ln in f if ln.strip()}
    except OSError:
        return set()


def append_history(urls: list):
    existing = []
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, encoding="utf-8") as f:
                existing = [ln.strip() for ln in f if ln.strip()]
        except OSError:
            existing = []
    combined = existing + [u for u in urls if u not in existing]
    combined = combined[-HISTORY_KEEP:]
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(combined) + "\n")
    except OSError as e:
        print(f"[history 写入失败] {e}", file=sys.stderr)


# ── 正文抓取：Google News 链接 → 真实 URL → Jina 全文 ────────────────────────
def decode_google_news_url(gn_url: str, timeout: int = 20):
    """把 Google News 跳转链接解码成原文真实 URL（batchexecute 接口）。失败返回 None。"""
    m = re.search(r"/articles/([^?]+)", gn_url)
    if not m:
        return None
    art_id = m.group(1)
    try:
        r = requests.get(f"https://news.google.com/rss/articles/{art_id}",
                         headers=UA, timeout=timeout)
        sig = re.search(r'data-n-a-sg="([^"]+)"', r.text)
        ts = re.search(r'data-n-a-ts="([^"]+)"', r.text)
        if not (sig and ts):
            return None
        inner = json.dumps([
            "garturlreq",
            [["X", "X", ["X", "X"], None, None, 1, 1, "US:en", None, 1,
              None, None, None, None, None, 0, 1],
             "X", "X", 1, [1, 1, 1], 1, 1, None, 0, 0, None, 0],
            art_id, ts.group(1), sig.group(1),
        ])
        body = "f.req=" + quote(json.dumps([[["Fbv4je", inner]]]))
        r2 = requests.post(
            "https://news.google.com/_/DotsSplashUi/data/batchexecute",
            headers={**UA, "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"},
            data=body, timeout=timeout)
        text = r2.text.replace('\\u003d', '=').replace('\\/', '/')
        mm = re.search(r'(https?://[^\\"]+)', text)
        return mm.group(1) if mm else None
    except Exception as e:
        print(f"[解码失败] {e}", file=sys.stderr)
        return None


_DISCLAIMER_RE = re.compile(
    r"terms of use|terms and conditions|privacy|cookie|by accessing|solicitation|"
    r"institutional investor|professional investor|all rights reserved|©|"
    r"select a role|accept delivery|jurisdiction", re.IGNORECASE)


def _norm(s: str) -> str:
    """归一化：仅留小写字母数字，便于跨标点比对标题。"""
    return re.sub(r'[^a-z0-9]+', ' ', s.lower()).strip()


def extract_body(md: str, title: str) -> str:
    """从 Jina 返回的 markdown 中剥离免责声明/导航，截取文章正文。"""
    idx = md.find("Markdown Content:")
    if idx != -1:
        md = md[idx + len("Markdown Content:"):]

    # 定位正文起点：取「归一化后包含完整标题」的最后一个标题行
    # （免责声明墙顶部也有同名标题，真正文是页面靠后的那一个）
    key = _norm(title)
    best = None
    if key:
        for h in re.finditer(r'(?m)^#{1,3}[ \t]+(.+?)[ \t]*$', md):
            if key in _norm(h.group(1)):
                best = h.start()
    if best is not None:
        md = md[best:]

    md = re.sub(r'!\[[^\]]*\]\([^)]*\)', '', md)          # 删图片
    md = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', md)        # 链接→文字
    lines = [ln for ln in md.splitlines() if not _DISCLAIMER_RE.search(ln)]
    md = re.sub(r'\n{3,}', '\n\n', "\n".join(lines)).strip()
    return md[:MAX_BODY_CHARS]


def fetch_fulltext(article: dict) -> bool:
    """为单篇文章解码真实 URL 并用 Jina 抓正文，写入 article['body']/['real_url']。
    成功返回 True；失败时 body 留空，由调用方回退到 RSS 摘要。"""
    real = decode_google_news_url(article["url"])
    if not real:
        return False
    article["real_url"] = real
    try:
        r = requests.get(f"https://r.jina.ai/{real}",
                         headers={**UA, "X-Return-Format": "markdown"}, timeout=45)
        if r.status_code != 200 or len(r.text) < 400:
            print(f"[Jina {r.status_code}] {real}", file=sys.stderr)
            return False
        body = extract_body(r.text, article["title"])
        if len(body) < 200:
            return False
        article["body"] = body
        return True
    except Exception as e:
        print(f"[Jina 抓取失败] {e}", file=sys.stderr)
        return False


# ── Groq 主题聚合（中英混合深度解读）─────────────────────────────────────────
SYSTEM_PROMPT = """你是为一位「外资投行 / ECM 志望」的就活生服务的华尔街研究中文深度解读编辑。下面给你的是从各大投行 / 独立研究机构【官方公开栏目】抓取的、与 AI 投资相关文章的【正文全文】（每篇带编号、机构名、英文原标题、正文）。

你的任务：基于正文里的【具体论据、数据、逻辑链】，写一份有深度、逻辑清晰的中文主题聚合解读。读者要的是"为什么"和"机制"，不是干巴巴的结论。中英混合：英文专业术语、机构英文名、文章原标题、关键英文概念保留英文，解读正文用简体中文。

【输出格式（严格遵守）】

📊 华尔街 AI 投资观点 · 主题深读

▌主题一：<主题名>

〔综述〕2-4 句，把本主题下各机构的核心分歧 / 共识讲清楚，点明这一主题为什么重要。

• <机构英文名>《英文原标题》【编号】

  ▸ 核心判断：<这家机构到底在说什么，1-2 句>

  ▸ 论据 & 数据：<引用正文里的具体数字 / 事实 / 因果链，2-3 句，这是重点，必须扎实>

  ▸ 投资启示：<方向（看多/看空/中性/上调/下调）+ 受益或受损的具体资产/行业/公司 + 一句话机制>

• <机构英文名>《英文原标题》【编号】

  ▸ 核心判断：……

  ▸ 论据 & 数据：……

  ▸ 投资启示：……

▌主题二：<主题名>
……

〔本期一句话〕用一句话点出本期所有文章合起来反映的最重要的市场信号。

【排版硬性要求】
- 三个小标题（核心判断 / 论据 & 数据 / 投资启示）之间【必须各空一行】，每个小标题独占一段，绝不允许把它们挤在相邻行里。
- 每个机构条目之间也空一行。务必保证在微信 markdown 里渲染为清晰分段。

【硬性规则】
- 数字一律【保留原文英文写法】，绝不换算成中文"亿/万亿"：如 USD 700bn、11→16 trillion、+7% CAGR、+16% YoY、25x P/E。这是为避免数量级翻译错误（billion=十亿，trillion=万亿），务必照搬原文数字与单位。
- 每个「论据 & 数据」至少含一个来自正文的具体数字或具体事实，并交代其因果/逻辑（不是只丢一个数字）。若正文确无量化数据，写明"（原文未给量化数据）"，但仍要用 1-2 句讲清该机构的定性逻辑。
- 必须抓住每篇文章的【核心论证链】，而非泛泛结论。例：若原文讲"capex 增速远超营收增速 → 现金流承压 → 变现(monetization)与效率是 AI 行情能否持续的关键"，就要把这条因果链复述清楚。
- 「投资启示」三要素齐全：①方向（看多/看空/中性/上调/下调）；②具体资产/行业/公司名；③一句话传导机制。严禁"影响市场情绪""产生深远影响""带来机遇"之类空话。
- 把跨机构的同主题观点聚成 2-4 个主题（如：AI 资本开支与变现 monetization、二阶受益（电力/数据中心/冷却/输电）、半导体与算力、AI 与 ECM/股票发行、宏观利率对 AI 估值的影响、区域机会等）。
- 【每一篇有效文章都必须出现】在某个主题下，不得静默丢弃；编号必须对应输入文章，绝不编造。
- 中英混合：英文专业术语、机构英文名、文章原标题保留英文，解读正文用简体中文。
- 不要输出来源链接（系统另附）、不要前言、不要"以下是"之类话术。
- 若某篇正文是招聘/导航/与 AI 投资无关，直接忽略；若全部无效，只输出一行：本期暂无官方 AI 投资观点更新。"""


def summarize_with_claude(articles: list) -> str:
    blocks = []
    for i, a in enumerate(articles, 1):
        seg = f"════ [{i}] ({a['inst']}) {a['title']} ════"
        if a.get("body"):
            seg += f"\n{a['body']}"
        elif a.get("summary"):
            seg += f"\n（仅摘要，未取到全文）{a['summary']}"
        blocks.append(seg)
    articles_text = "\n\n".join(blocks)

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    msg = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=CLAUDE_MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": f"【文章正文列表】\n\n{articles_text}"}],
    )
    return "".join(b.text for b in msg.content if b.type == "text").strip()


def build_source_list(articles: list) -> str:
    lines = ["━━━━━━━━━━━━━", f"📎 本期来源（{len(articles)} 篇）\n"]
    for i, a in enumerate(articles, 1):
        url = a.get("real_url") or a["url"]      # 优先用解码后的原文真实链接
        lines.append(f"【{i}】[{a['inst']}] {a['title']}\n{url}\n")
    return "\n".join(lines)


# ── 微信推送（Server酱）─────────────────────────────────────────────────────
def push_wechat(content: str, send_key: str, weekday_label: str, date_str: str) -> bool:
    MAX_DESP_LEN = 30000   # Server酱 turbo 支持约 32KB，篇数增多放宽上限
    if len(content) > MAX_DESP_LEN:
        content = content[:MAX_DESP_LEN] + "\n\n…（内容过长，已截断）"
    try:
        resp = requests.post(
            f"https://sctapi.ftqq.com/{send_key}.send",
            data={"title": f"🏦 华尔街AI观点 {weekday_label} {date_str}", "desp": content},
            timeout=15,
        )
        body = resp.json()
        return body.get("code", body.get("errno", -1)) == 0
    except Exception as e:
        print(f"[推送异常] {e}", file=sys.stderr)
        return False


# ── 入口 ────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--slot", default=None,
                        help="monday / friday（仅用于标题标注，缺省则按当天推断）")
    parser.add_argument("--dry-run", action="store_true",
                        help="只抓取+整理并打印，不推送微信、不写 history")
    args = parser.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("[错误] 请设置 ANTHROPIC_API_KEY（console.anthropic.com）", file=sys.stderr)
        sys.exit(1)

    now = datetime.now(JST)
    date_str = now.strftime("%Y/%m/%d")
    if args.slot == "monday":
        weekday_label = "周一"
    elif args.slot == "friday":
        weekday_label = "周五"
    else:
        weekday_label = WEEKDAY_CN[now.weekday()]

    cutoff_dt = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)
    history = load_history()
    seen_links = set(history)
    seen_titles = set()

    articles = []
    for inst_name, domains in INSTITUTIONS:
        items = fetch_institution(inst_name, domains, cutoff_dt, seen_links, seen_titles)
        print(f"  {inst_name}: {len(items)} 条新文章")
        articles.extend(items)
        time.sleep(1)   # 礼貌限速

    if not articles:
        print("[提示] 本期未抓到任何新的官方 AI 投资文章，跳过推送")
        return

    articles = articles[:MAX_ARTICLES]

    print(f"\n合计 {len(articles)} 条，正在抓取各篇正文全文...")
    got = 0
    for a in articles:
        ok = fetch_fulltext(a)
        got += ok
        print(f"  {'✓全文' if ok else '✗仅摘要'}  [{a['inst']}] {a['title'][:50]}")
        time.sleep(1.5)   # 礼貌限速，规避 Jina 速率限制
    print(f"全文抓取成功 {got}/{len(articles)} 篇\n")

    print("正在用 Claude 主题深读整理...\n")
    themed = summarize_with_claude(articles)
    source_list = build_source_list(articles)
    result = f"{themed}\n\n{source_list}"

    print(result)
    print()

    if args.dry_run:
        print("[dry-run] 已跳过微信推送与 history 写入")
        return

    send_key = os.environ.get("SERVERCHAN_KEY")
    if send_key:
        ok = push_wechat(result, send_key, weekday_label, date_str)
        print("[微信推送] ✓ 成功" if ok else "[微信推送] ✗ 失败，请检查 SERVERCHAN_KEY")
        if ok:
            append_history([a["url"] for a in articles])
    else:
        print("[提示] 未设置 SERVERCHAN_KEY，已跳过微信推送")


if __name__ == "__main__":
    main()
