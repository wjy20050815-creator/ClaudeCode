#!/usr/bin/env python3
"""
脑科学知识推送 Agent
PubMed 学术论文 + 权威健康科学媒体 → Groq AI 摘要 → Server酱 → 微信

环境变量：
  GROQ_API_KEY     — Groq API 密钥（必须）
  NEWSAPI_KEY      — NewsAPI 密钥（可选，已有则自动使用）
  SERVERCHAN_KEY   — Server酱 SendKey（可选，未设置则只打印）
"""

import argparse
import os
import random
import sys
import requests
import pytz
import xml.etree.ElementTree as ET
from datetime import datetime
from groq import Groq
from pathlib import Path

HISTORY_FILE = Path(__file__).parent / "history.txt"
HISTORY_MAX  = 60

# 权威健康/神经科学媒体白名单（NewsAPI domains 参数）
HEALTH_DOMAINS = (
    "scientificamerican.com,sciencedaily.com,medicalnewstoday.com,"
    "psychologytoday.com,health.harvard.edu,nature.com,newscientist.com"
)

SLOT_CONFIG = {
    "morning": {
        "theme": "早晨认知与效率",
        "pubmed_queries": [
            "cortisol awakening response cognition performance",
            "morning smartphone use attention cognitive impairment",
            "morning routine habit formation brain prefrontal",
            "acute exercise cognitive performance working memory attention",
            "caffeine alertness attention cognitive performance morning",
            "circadian rhythm chronotype morning cognitive performance",
            "sleep inertia grogginess waking cognitive function",
            "breakfast nutrition cognitive function brain glucose",
            "morning light exposure serotonin mood regulation",
            "dopamine motivation reward morning productivity",
            "meditation mindfulness morning prefrontal cortex",
            "cold exposure norepinephrine alertness brain",
            "hydration dehydration cognitive performance brain",
        ],
        "newsapi_query": "brain morning cognitive focus attention wake alertness exercise caffeine",
        "emoji": "🌅",
        "label": "晨间脑科学",
    },
    "night": {
        "theme": "夜间睡眠与大脑恢复",
        "pubmed_queries": [
            "sleep memory consolidation hippocampus synaptic",
            "blue light exposure melatonin sleep quality",
            "glymphatic system sleep brain waste clearance",
            "dream REM sleep emotional processing amygdala",
            "sleep deprivation prefrontal cortex decision making",
            "circadian disruption neuroinflammation brain health",
            "napping cognitive restoration memory enhancement",
            "sleep spindles thalamus learning consolidation",
            "gut microbiome sleep quality brain axis",
            "evening routine wind down parasympathetic nervous",
        ],
        "newsapi_query": "sleep brain health memory neuroscience circadian recovery",
        "emoji": "🌙",
        "label": "夜间脑科学",
    },
}

MAX_RETRIES = 3

SYSTEM_PROMPT = """你是一位专业的神经科学科普编辑。你的任务是综合以下真实学术论文和权威健康媒体文章中的发现，改写为通俗易懂的中文科普推送。可以融合多条来源的内容，但核心发现必须来自所提供的材料，不得凭空编造。

【原始来源材料】
{sources}

【已推送过的话题（严禁选取相同话题，必须另选新角度）】
{history}

【当前主题方向】
{theme}

【输出格式（严格遵守，不得添加任何前缀或后缀）】
📌 知识点（15字以内标题，概括核心发现）

正文：3-4句话，依次说明：① 研究发现了什么 ② 背后的神经/认知机制 ③ 对日常生活的具体影响

💡 实践建议：一条今天就能执行的具体行动

📎 来源：[期刊或媒体名称，若综合多条则列主要来源，逗号分隔]

【约束】
- 必须基于上方提供的来源材料，不得凭空编造
- 来源名称填写期刊名或媒体名（如 Nature Neuroscience、ScienceDaily、Harvard Health）
- 简体中文，通俗易懂，总字数 150-200 字（不含来源行）
- 只输出正文，无额外说明"""


def load_history() -> list[str]:
    if not HISTORY_FILE.exists():
        return []
    lines = HISTORY_FILE.read_text(encoding="utf-8").strip().splitlines()
    return [l.strip() for l in lines if l.strip()][-HISTORY_MAX:]


STOPWORDS = set("与和的对在中了是也为及其从到")


def _content_chars(s: str) -> set[str]:
    return set(s) - STOPWORDS


def is_duplicate(topic: str, history: list[str]) -> bool:
    if topic in history:
        return True
    tc = _content_chars(topic)
    for h in history:
        if topic in h or h in topic:
            return True
        hc = _content_chars(h)
        overlap = len(tc & hc) / max(len(tc | hc), 1)
        if overlap > 0.5:
            return True
    return False


def save_history(topic: str) -> None:
    history = load_history()
    history.append(topic)
    HISTORY_FILE.write_text("\n".join(history[-HISTORY_MAX:]) + "\n", encoding="utf-8")


# ── PubMed（免费，无需 API Key）────────────────────────────────────────────────
def fetch_pubmed(queries: list[str], max_per_query: int = 3) -> list[dict]:
    base     = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    articles = []
    seen_ids: set[str] = set()

    for query in queries:
        try:
            search = requests.get(
                f"{base}/esearch.fcgi",
                params={
                    "db": "pubmed", "term": query,
                    "retmax": max_per_query, "sort": "date",
                    "retmode": "json", "datetype": "pdat",
                    "reldate": 365,          # 最近 1 年
                },
                timeout=15,
            )
            ids = [i for i in search.json().get("esearchresult", {}).get("idlist", [])
                   if i not in seen_ids]
            if not ids:
                continue
            seen_ids.update(ids)

            fetch = requests.get(
                f"{base}/efetch.fcgi",
                params={
                    "db": "pubmed", "id": ",".join(ids),
                    "rettype": "abstract", "retmode": "xml",
                },
                timeout=15,
            )
            root = ET.fromstring(fetch.text)
            for art in root.findall(".//PubmedArticle"):
                title_el   = art.find(".//ArticleTitle")
                abst_el    = art.find(".//AbstractText")
                journal_el = art.find(".//Journal/Title")
                if title_el is None:
                    continue
                title   = "".join(title_el.itertext()).strip()
                abstract = "".join(abst_el.itertext()).strip()[:600] if abst_el is not None else ""
                journal  = (journal_el.text or "PubMed").strip() if journal_el is not None else "PubMed"
                if title:
                    articles.append({"source": journal, "title": title, "summary": abstract})
        except Exception as e:
            print(f"[PubMed 失败] {query!r}: {e}", file=sys.stderr)

    return articles


# ── NewsAPI（权威健康科学媒体白名单）─────────────────────────────────────────────
def fetch_health_news(api_key: str, query: str) -> list[dict]:
    articles = []
    try:
        resp = requests.get(
            "https://newsapi.org/v2/everything",
            params={
                "q":        query,
                "domains":  HEALTH_DOMAINS,
                "language": "en",
                "sortBy":   "publishedAt",
                "pageSize": 10,
                "apiKey":   api_key,
            },
            timeout=15,
        )
        resp.raise_for_status()
        for a in resp.json().get("articles", []):
            title = (a.get("title") or "").strip()
            if not title:
                continue
            articles.append({
                "source":  a.get("source", {}).get("name") or "Health News",
                "title":   title,
                "summary": (a.get("description") or "")[:400].strip(),
            })
    except Exception as e:
        print(f"[NewsAPI 失败] {e}", file=sys.stderr)
    return articles


# ── Groq AI 摘要 ──────────────────────────────────────────────────────────────
def summarize(articles: list[dict], slot: str, history: list[str]) -> tuple[str, str]:
    cfg          = SLOT_CONFIG[slot]
    sources_text = "\n\n".join(
        f"[{a['source']}] {a['title']}\n{a['summary']}" if a["summary"]
        else f"[{a['source']}] {a['title']}"
        for a in articles
    )
    history_text = "\n".join(f"- {h}" for h in history) if history else "（暂无）"

    client   = Groq(api_key=os.environ["GROQ_API_KEY"])
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        max_tokens=600,
        temperature=0.4,
        messages=[
            {
                "role": "system",
                "content": SYSTEM_PROMPT.format(
                    sources=sources_text,
                    history=history_text,
                    theme=cfg["theme"],
                ),
            },
            {"role": "user", "content": "请基于以上来源材料，输出今日脑科学知识。"},
        ],
    )
    content    = response.choices[0].message.content.strip()
    first_line = content.splitlines()[0].replace("📌", "").strip()
    return content, first_line


def validate_content(content: str) -> bool:
    return "📌" in content and "💡" in content and "📎" in content


# ── 微信推送（Server酱）───────────────────────────────────────────────────────
def push_wechat(content: str, slot: str, send_key: str) -> bool:
    cfg = SLOT_CONFIG[slot]
    jst = pytz.timezone("Asia/Tokyo")
    now = datetime.now(jst).strftime("%Y/%m/%d %H:%M")
    try:
        resp = requests.post(
            f"https://sctapi.ftqq.com/{send_key}.send",
            data={"title": f"{cfg['emoji']} {cfg['label']} {now}", "desp": content},
            timeout=15,
        )
        body = resp.json()
        return body.get("code", body.get("errno", -1)) == 0
    except Exception as e:
        print(f"[推送异常] {e}", file=sys.stderr)
        return False


# ── 入口 ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--slot", choices=["morning", "night"], required=True,
        help="推送时段：morning（早晨开机触发）或 night（22:30 定时触发）",
    )
    args = parser.parse_args()

    if not os.environ.get("GROQ_API_KEY"):
        print("[错误] 请设置 GROQ_API_KEY（免费：console.groq.com/keys）", file=sys.stderr)
        sys.exit(1)

    cfg = SLOT_CONFIG[args.slot]
    print(f"[脑科学推送] 时段：{args.slot} — {cfg['theme']}")

    history = load_history()
    print(f"  已记录历史话题数：{len(history)}")

    articles: list[dict] = []

    print("正在抓取 PubMed 学术论文...")
    pubmed_articles = fetch_pubmed(cfg["pubmed_queries"])
    print(f"  获取到 {len(pubmed_articles)} 篇")
    articles.extend(pubmed_articles)

    newsapi_key = os.environ.get("NEWSAPI_KEY")
    if newsapi_key:
        print("正在抓取权威健康科学媒体文章...")
        news_articles = fetch_health_news(newsapi_key, cfg["newsapi_query"])
        print(f"  获取到 {len(news_articles)} 篇")
        articles.extend(news_articles)

    if not articles:
        print("[警告] 未能获取到任何来源材料，跳过本次推送", file=sys.stderr)
        sys.exit(1)

    random.shuffle(articles)

    print(f"\n合计 {len(articles)} 条来源，正在用 AI 整理...\n")

    content = None
    topic = None
    rejected: list[str] = []

    for attempt in range(1, MAX_RETRIES + 1):
        extended_history = history + rejected
        content, topic = summarize(articles, args.slot, extended_history)

        if not content:
            print(f"[尝试 {attempt}/{MAX_RETRIES}] AI 未能生成有效内容", file=sys.stderr)
            continue

        print(f"生成内容：\n{content}\n")

        if not validate_content(content):
            print(f"[尝试 {attempt}/{MAX_RETRIES}] AI 输出缺少必要字段（📌/💡/📎）", file=sys.stderr)
            continue

        if is_duplicate(topic, history):
            print(f"[尝试 {attempt}/{MAX_RETRIES}] 话题「{topic}」与历史重复，重试中...", file=sys.stderr)
            rejected.append(topic)
            content = None
            continue

        break

    if content is None:
        print(f"[警告] {MAX_RETRIES} 次尝试均未能生成新话题，跳过本次推送", file=sys.stderr)
        sys.exit(1)

    send_key = os.environ.get("SERVERCHAN_KEY")
    if send_key:
        ok = push_wechat(content, args.slot, send_key)
        if ok:
            save_history(topic)
            print("[微信推送] ✓ 成功")
        else:
            print("[微信推送] ✗ 失败，请检查 SERVERCHAN_KEY 是否正确")
            sys.exit(1)
    else:
        print("[提示] 未设置 SERVERCHAN_KEY，已跳过微信推送（话题未记录历史）")


if __name__ == "__main__":
    main()
