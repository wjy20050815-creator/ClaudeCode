#!/usr/bin/env python3
"""
财经新闻播报 Agent
NewsAPI → Groq AI 整理 → 微信推送

环境变量：
  GROQ_API_KEY       — Groq API 密钥（必须，免费：console.groq.com/keys）
  NEWSAPI_KEY        — NewsAPI 密钥（免费：newsapi.org）
  SERVERCHAN_KEY     — Server酱 SendKey（可选，未设置则只打印）
"""

import argparse
import os
import re
import sys
import time
import requests
import pytz
import yfinance as yf
from datetime import datetime, timezone, timedelta, time as dt_time
from groq import Groq

# ── 行情数据源 ──────────────────────────────────────────────────────────────
# (display_name, symbol, market, currency)
# market: "us"   → yfinance + fast_info.previous_close
#         "jp"   → yfinance + history（JST 时区判断前收）
#         "sina" → 新浪财经 API（上海黄金交易所）
WATCHLIST = [
    ("S&P 500",      "^GSPC",     "us",   "USD"),
    ("纳斯达克",      "^IXIC",     "us",   "USD"),
    ("纽约黄金",      "GC=F",      "us",   "USD"),
    ("美元兑日元",    "USDJPY=X",  "us",   "JPY_RATE"),
    ("人民币对日元",  "CNYJPY=X",  "us",   "CNY_JPY"),
    ("上海黄金连续",  "nf_AU0",    "sina", "CNY"),
    ("三井金属",      "5706.T",    "jp",   "JPY"),
    ("JX金属",        "5016.T",    "jp",   "JPY"),
    ("软银集团",      "9984.T",    "jp",   "JPY"),
]


def market_status(market: str) -> str:
    """返回市场状态标识；正常交易时段内返回空字符串。不含节假日判断。"""
    now_utc = datetime.now(timezone.utc)
    weekday = now_utc.weekday()  # 0=Mon … 6=Sun

    if weekday >= 5:
        return "[休市]"

    if market == "us":
        t = now_utc.astimezone(pytz.timezone("America/New_York")).time()
        if t < dt_time(9, 30):
            return "[未开盘]"
        if t > dt_time(16, 0):
            return "[已收盘]"
        return ""

    if market == "jp":
        t = now_utc.astimezone(pytz.timezone("Asia/Tokyo")).time()
        if t < dt_time(9, 0):
            return "[未开盘]"
        if dt_time(11, 30) < t < dt_time(12, 30):
            return "[午休]"
        if t > dt_time(15, 30):
            return "[已收盘]"
        return ""

    if market == "sina":
        t = now_utc.astimezone(pytz.timezone("Asia/Shanghai")).time()
        if dt_time(9, 0) <= t <= dt_time(15, 30):
            return ""
        if dt_time(20, 0) <= t <= dt_time(23, 30):
            return ""
        if t < dt_time(9, 0):
            return "[未开盘]"
        return "[休市]"  # 午后收盘至夜盘开盘之间，或夜盘收盘后

    return ""


def fetch_sina_price(symbol: str) -> tuple[float, float]:
    """从新浪财经 API 获取价格，返回 (current_price, prev_close)。"""
    url = f"https://hq.sinajs.cn/list={symbol}"
    headers = {
        "Referer": "https://finance.sina.com.cn/",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
    }
    resp = requests.get(url, headers=headers, timeout=10)
    resp.raise_for_status()
    match = re.search(r'"([^"]*)"', resp.text)
    if not match or not match.group(1).strip():
        raise ValueError("休市或暂无数据")
    fields = match.group(1).split(",")
    if len(fields) < 3:
        raise ValueError(f"字段不足（{len(fields)} 个）")
    # SHFE 期货连续合约（20+字段）：[6]=最新价，[2]=昨结算价
    # SGE 现货（~12字段）：[1]=现价，[2]=涨跌额
    if len(fields) > 15:
        price = float(fields[6])
        prev  = float(fields[2])
    else:
        price  = float(fields[1])
        change = float(fields[2])
        prev   = price - change
    return price, prev


def fetch_stock_prices(now_str: str) -> str:
    lines = [f"📈 主要指数行情（{now_str}，约15分钟延迟）\n"]
    for name, symbol, market, currency in WATCHLIST:
        try:
            if market == "sina":
                price, prev = fetch_sina_price(symbol)
            else:
                t     = yf.Ticker(symbol)
                fi    = t.fast_info
                price = fi.last_price
                if market == "jp":
                    hist      = t.history(period="5d")["Close"]
                    today_jst = datetime.now(pytz.timezone("Asia/Tokyo")).date()
                    if hist.index[-1].date() == today_jst:
                        prev = hist.iloc[-2]
                    else:
                        price = hist.iloc[-1]
                        prev  = hist.iloc[-2]
                else:
                    prev = fi.previous_close

            if price is None or price != price:
                raise ValueError("价格数据无效（NaN）")
            if prev is None or prev != prev or prev == 0:
                raise ValueError("昨收数据无效")
            chg    = price - prev
            pct    = chg / prev * 100
            arrow  = "▲" if chg >= 0 else "▼"
            sign   = "+" if chg >= 0 else ""
            status = market_status(market)
            suffix = f"  {status}" if status else ""

            if currency == "JPY":
                lines.append(f"• {name:<8} ¥{price:>9,.0f}  {arrow} {sign}{chg:,.0f} ({sign}{pct:.2f}%){suffix}\n")
            elif currency == "CNY":
                lines.append(f"• {name:<8} ¥{price:>9,.2f}  {arrow} {sign}{chg:,.2f} ({sign}{pct:.2f}%){suffix}\n")
            elif currency == "JPY_RATE":
                lines.append(f"• {name:<8} {price:>9.2f}  {arrow} {sign}{chg:.2f} ({sign}{pct:.2f}%){suffix}\n")
            elif currency == "CNY_JPY":
                lines.append(f"• {name:<8} {price:>9.4f}  {arrow} {sign}{chg:.4f} ({sign}{pct:.2f}%){suffix}\n")
            else:  # USD
                lines.append(f"• {name:<8} ${price:>9,.2f}  {arrow} {sign}{chg:,.2f} ({sign}{pct:.2f}%){suffix}\n")
        except Exception as e:
            lines.append(f"• {name}: 数据获取失败 ({e})\n")
    return "\n".join(lines)


# ── catalyst-calendar：未来 7 天事件 ─────────────────────────────────────────
def fetch_catalyst_section(ref_dt: datetime) -> str:
    """对 WATCHLIST 里的个股（指数/汇率/商品跳过）查询未来 7 天财报日。
    无事件时返回空串，由调用方决定是否拼接。"""
    horizon_end = ref_dt.date() + timedelta(days=7)
    events = []
    for name, symbol, market, currency in WATCHLIST:
        if market == "sina":
            continue
        if currency in ("JPY_RATE", "CNY_JPY"):
            continue
        if symbol.startswith("^") or symbol.endswith("=F"):
            continue
        try:
            t   = yf.Ticker(symbol)
            cal = t.calendar
            ed  = None
            if isinstance(cal, dict):
                raw = cal.get("Earnings Date")
                if raw:
                    ed = raw[0] if isinstance(raw, list) else raw
            if ed is None:
                continue
            ed_date = ed.date() if hasattr(ed, "date") else ed
            if ref_dt.date() <= ed_date <= horizon_end:
                events.append((ed_date, name, symbol))
        except Exception as e:
            print(f"[catalyst {name}] {e}", file=sys.stderr)

    if not events:
        return ""
    events.sort()
    lines = ["📅 未来 7 天事件\n"]
    for ed_date, name, symbol in events:
        lines.append(f"• {ed_date.strftime('%m/%d')}  {name}（{symbol}）财报\n")
    return "\n".join(lines)


# ── 系统提示词 ──────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """你是一个专业的财经新闻分析助手，负责定时推送高质量的财经新闻摘要。

【任务目标】
根据提供的原始新闻标题和摘要，按三个独立专区整理输出，帮助用户快速掌握市场动态。

【输出格式（必须严格遵守，三个专区依次输出）】

今日播报（时间：{now}）

━━━ 📊 财经要闻 ━━━

1. 【标题】
   - 摘要：用2-3句话说明发生了什么
   - 影响：基于事实地简要分析对市场的潜在影响
   - 📎 来源名称 | https://原文链接

（最多5条，按重要性排序）
筛选范围：宏观经济（CPI、利率、政策）、股票市场（美股/日股/A股）、国际金融（美联储）、大公司重大事件（财报、并购、监管）、期货（黄金白银原油）。过滤低价值信息。
行情类新闻准入标准：凡内容为"某资产/商品/指数价格上涨/下跌"的新闻，若无具体涨跌幅（百分比或绝对值），则视为无效信息，不得纳入播报——该类方向性信息已由行情栏覆盖。

━━━ 🤖 AI 专区 ━━━

1. 【标题】
   - 摘要：用2-3句话说明发生了什么
   - 影响：简要分析对 AI 产业或市场的潜在影响
   - 📎 来源名称 | https://原文链接

（最多5条，按重要性排序）
筛选范围：
- 新模型或重大功能发布（如 GPT-5、Claude 4、Gemini 等）
- 主要 AI 公司动态（OpenAI、Anthropic、Google DeepMind、xAI、Meta AI、Mistral 等）
- AI 公司高管或 CEO 的重要发言（Sam Altman、Jensen Huang、Dario Amodei、Elon Musk 等）
- 半导体与芯片产业（Nvidia、AMD、Intel、台积电、三星等重要动态）
- AI 相关重大融资、并购、监管政策
- AI 对行业的颠覆性影响（医疗、金融、能源等）

严格排除以下内容：
- 个人或小团队发布的开源工具、Python 包、GitHub 项目
- 教程、课程、博客、技术文章
- 热度低、来源不知名的软件发布公告
- 无市场影响的产品更新或版本迭代
- 硬件新品发布（新 iPhone、新 Mac、新平板等），除非该新品的核心卖点是 AI 功能（如 Apple Intelligence 重大更新、端侧 AI 突破等）
- 苹果、三星等消费电子公司的常规产品迭代，除非与 AI 战略直接相关

如无相关新闻，输出：暂无相关动态

━━━ ⚔️ 美伊局势 ━━━

1. 【标题】
   - 摘要：用2-3句话说明发生了什么
   - 影响：简要分析对地区局势或金融市场的潜在影响
   - 📎 来源名称 | https://原文链接

（最多5条，按时间倒序）
筛选范围：美国与伊朗之间的外交、军事、制裁、核协议相关动态，以及中东局势对能源市场的影响。
如无相关新闻，输出：暂无相关动态

【风格要求】
- 使用简体中文
- 语言简洁、专业
- 不使用口语表达
- 不输出三个专区以外的任何内容、解释或说明

【行为约束】
- 不编造信息，不重复旧闻
- 每条新闻只能出现在一个专区：一旦某条新闻已被纳入某专区，不得在其他专区再次引用同一事件或同一文章，即使该文章的内容横跨多个专区的主题范围也不例外
- 每条新闻必须附来源名称和原文 URL（从输入数据的 URL 字段原样复制，完整保留，不得截断或修改）
- 若某条新闻无 URL，省略 📎 行
- 财经要闻如无内容，输出：当前无重要财经新闻更新

【数字保留规则】
摘要中凡涉及价格、数量、比例变动（涨跌幅、融资额、裁员人数、降价幅度等），必须保留至少一个具体数字。若原文确实未提供任何量化数据，在摘要末尾注明（原文无具体数据）。

【影响分析规则】
影响分析必须同时包含：①受影响的具体资产/行业/公司名称；②方向（受益/受损/上涨/下跌）；③一句话机制说明。
禁止使用以下泛化表述："可能影响市场稳定"、"对经济产生深远影响"、"引发更多竞争"、"影响投资者情绪"等无实质内容的套话。

【来源优先级】
同一事件有多个来源时，优先引用 Reuters、Bloomberg、AP、Financial Times、WSJ、CNBC 等主流财经媒体。加密货币媒体（如 Crypto Briefing、CoinDesk 等）不得作为宏观经济、能源或地缘政治话题的主要来源。"""


# ── NewsAPI（英文主源）──────────────────────────────────────────────────────
def fetch_newsapi(api_key: str, hours: int = 36, seen: set = None, as_of=None) -> list:
    if seen is None:
        seen = set()
    reference = (as_of or datetime.now(timezone.utc)).astimezone(timezone.utc)
    cutoff_dt = reference - timedelta(hours=hours)
    cutoff    = cutoff_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    to_time   = reference.strftime("%Y-%m-%dT%H:%M:%SZ")
    articles  = []

    queries = [
        ("top-headlines", {"category": "business", "language": "en", "pageSize": 8}),
        ("everything",    {"q": 'Fed OR "interest rate" OR "S&P 500" OR gold OR oil OR GDP',
                           "language": "en", "sortBy": "publishedAt",
                           "from": cutoff, "to": to_time, "pageSize": 9}),
        ("everything",    {"q": '(OpenAI OR Anthropic OR Nvidia OR "Google DeepMind" OR xAI OR "Meta AI" OR Mistral OR "AI model" OR "language model" OR semiconductor OR chip OR "Sam Altman" OR "Jensen Huang" OR "Dario Amodei" OR "Sundar Pichai") OR (Iran OR "US-Iran" OR "Iran nuclear" OR "Iran sanctions" OR "Iran missile")',
                           "language": "en", "sortBy": "publishedAt",
                           "from": cutoff, "to": to_time, "pageSize": 8}),
    ]

    for endpoint, params in queries:
        try:
            resp = requests.get(
                f"https://newsapi.org/v2/{endpoint}",
                params={**params, "apiKey": api_key},
                timeout=15,
            )
            resp.raise_for_status()
            for a in resp.json().get("articles", []):
                title = (a.get("title") or "").strip()
                if not title or title in seen:
                    continue
                pub_str = a.get("publishedAt") or ""
                if pub_str:
                    try:
                        pub_dt = datetime.fromisoformat(pub_str.replace("Z", "+00:00"))
                        if pub_dt < cutoff_dt or pub_dt > reference:
                            continue
                    except (ValueError, AttributeError):
                        pass
                seen.add(title)
                articles.append({
                    "source":  a.get("source", {}).get("name") or "NewsAPI",
                    "title":   title,
                    "summary": (a.get("description") or "")[:300].strip(),
                    "url":     a.get("url") or "",
                })
        except Exception as e:
            print(f"[NewsAPI 失败] {endpoint}: {e}", file=sys.stderr)

    return articles


# ── GNews（备用源）──────────────────────────────────────────────────────────
def fetch_gnews(api_key: str, hours: int = 36, seen: set = None, as_of=None) -> list:
    if seen is None:
        seen = set()
    reference = (as_of or datetime.now(timezone.utc)).astimezone(timezone.utc)
    cutoff_dt = reference - timedelta(hours=hours)
    cutoff    = cutoff_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    to_time   = reference.strftime("%Y-%m-%dT%H:%M:%SZ")
    articles  = []

    queries = [
        {"q": "business OR economy OR \"stock market\" OR \"interest rate\" OR gold OR oil", "max": 10},
        {"q": 'OpenAI OR Anthropic OR Nvidia OR "AI model" OR semiconductor OR "Sam Altman" OR "Jensen Huang" OR "Dario Amodei"', "max": 10},
        {"q": 'Iran OR "US-Iran" OR "Iran nuclear" OR "Iran sanctions" OR "Iran missile"', "max": 10},
    ]

    for params in queries:
        try:
            resp = requests.get(
                "https://gnews.io/api/v4/search",
                params={
                    **params,
                    "lang":    "en",
                    "sortby":  "publishedAt",
                    "from":    cutoff,
                    "to":      to_time,
                    "apikey":  api_key,
                },
                timeout=15,
            )
            resp.raise_for_status()
            for a in resp.json().get("articles", []):
                title = (a.get("title") or "").strip()
                if not title or title in seen:
                    continue
                pub_str = a.get("publishedAt") or ""
                if pub_str:
                    try:
                        pub_dt = datetime.fromisoformat(pub_str.replace("Z", "+00:00"))
                        if pub_dt < cutoff_dt or pub_dt > reference:
                            continue
                    except (ValueError, AttributeError):
                        pass
                seen.add(title)
                articles.append({
                    "source":  a.get("source", {}).get("name") or "GNews",
                    "title":   title,
                    "summary": (a.get("description") or "")[:300].strip(),
                    "url":     a.get("url") or "",
                })
        except Exception as e:
            print(f"[GNews 失败] {e}", file=sys.stderr)
        time.sleep(1)

    return articles


# ── AI 输出跨专区去重 ────────────────────────────────────────────────────────
_SECTION_HDR = re.compile(r'(━{3}[^━\n]+━{3})')
_ITEM_START  = re.compile(r'(?=^\d+\. 【)', re.MULTILINE)
_ITEM_NUM    = re.compile(r'^\d+\.')
_ITEM_URL    = re.compile(r'📎[^|]+\|\s*(https?://\S+)')
_ITEM_TITLE  = re.compile(r'【([^】]+)】')


def dedup_sections(text: str) -> str:
    """Remove items from later sections whose URL or title already appeared in an earlier section."""
    seen_urls   = set()
    seen_titles = set()
    parts       = _SECTION_HDR.split(text)
    result      = []

    for i, part in enumerate(parts):
        if _SECTION_HDR.fullmatch(part.strip()):
            result.append(part)
            continue
        if i == 0:
            result.append(part)
            continue

        segments   = _ITEM_START.split(part)
        pre_items  = segments[0]
        kept       = []

        for item in segments[1:]:
            url_m   = _ITEM_URL.search(item)
            title_m = _ITEM_TITLE.search(item)
            url     = url_m.group(1).rstrip(')') if url_m else None
            title   = title_m.group(1)           if title_m else None

            if (url and url in seen_urls) or (title and title in seen_titles):
                continue

            if url:   seen_urls.add(url)
            if title: seen_titles.add(title)
            kept.append(item)

        renumbered = [_ITEM_NUM.sub(f'{idx}.', item, count=1)
                      for idx, item in enumerate(kept, 1)]
        result.append(pre_items + ''.join(renumbered))

    return ''.join(result)


# ── Groq AI 摘要 ────────────────────────────────────────────────────────────
MAX_ARTICLES_TO_GROQ = 25
MAX_SUMMARY_CHARS    = 150


def summarize_with_groq(articles: list, now_str: str, stock_section: str = "") -> str:
    if not articles:
        return "当前无重要财经新闻更新"

    articles = articles[:MAX_ARTICLES_TO_GROQ]

    def fmt(a: dict) -> str:
        parts = [f"[{a['source']}] {a['title']}"]
        if a.get("url"):
            parts.append(f"URL: {a['url']}")
        if a.get("summary"):
            parts.append(a["summary"][:MAX_SUMMARY_CHARS])
        return "\n".join(parts)

    articles_text = "\n\n".join(fmt(a) for a in articles)

    user_content = (
        f"【今日实时行情（可在分析价格相关新闻时引用具体数字）】\n{stock_section}\n\n"
        f"【原始新闻列表】\n{articles_text}"
    ) if stock_section else articles_text

    client = Groq(api_key=os.environ["GROQ_API_KEY"])
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        max_tokens=3000,
        messages=[
            {
                "role": "system",
                "content": SYSTEM_PROMPT.format(now=now_str),
            },
            {
                "role": "user",
                "content": user_content,
            },
        ],
    )
    return response.choices[0].message.content.strip()


# ── 微信推送（Server酱）─────────────────────────────────────────────────────
def push_wechat(content: str, send_key: str, as_of=None) -> bool:
    jst = pytz.timezone("Asia/Tokyo")
    ref = as_of.astimezone(jst) if as_of else datetime.now(jst)
    jst_time = ref.strftime("%Y/%m/%d %H:%M")
    suffix = "（补）" if as_of else ""
    MAX_DESP_LEN = 4900
    if len(content) > MAX_DESP_LEN:
        content = content[:MAX_DESP_LEN] + "\n\n…（内容过长，已截断）"
    try:
        resp = requests.post(
            f"https://sctapi.ftqq.com/{send_key}.send",
            data={"title": f"📊 财经要闻 {jst_time}{suffix}", "desp": content},
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
    parser.add_argument(
        "--as-of", default=None,
        help="补跑用：触发时间点（JST，格式 YYYY-MM-DDTHH:MM），以此为基准抓取对应时段新闻",
    )
    args = parser.parse_args()

    groq_key    = os.environ.get("GROQ_API_KEY")
    newsapi_key = os.environ.get("NEWSAPI_KEY")
    gnews_key   = os.environ.get("GNEWS_KEY")

    if not groq_key:
        print("[错误] 请设置 GROQ_API_KEY（免费：console.groq.com/keys）", file=sys.stderr)
        sys.exit(1)
    if not newsapi_key:
        print("[错误] 请设置 NEWSAPI_KEY（免费：newsapi.org）", file=sys.stderr)
        sys.exit(1)

    jst = pytz.timezone("Asia/Tokyo")
    if args.as_of:
        as_of = jst.localize(datetime.fromisoformat(args.as_of))
        print(f"[补跑模式] 基准时间：{args.as_of} JST")
    else:
        as_of = None

    market_now_str = (as_of or datetime.now(jst)).strftime("%Y年%m月%d日 %H:%M JST")
    now_str = market_now_str + "（补跑）" if as_of else market_now_str

    articles = []
    seen     = set()

    print("正在抓取 NewsAPI 英文财经新闻...")
    na = fetch_newsapi(newsapi_key, hours=36, seen=seen, as_of=as_of)
    print(f"  获取到 {len(na)} 条")
    articles.extend(na)

    if gnews_key:
        print("正在抓取 GNews 英文财经新闻...")
        gn = fetch_gnews(gnews_key, hours=36, seen=seen, as_of=as_of)
        print(f"  获取到 {len(gn)} 条")
        articles.extend(gn)
    else:
        print("[提示] 未设置 GNEWS_KEY，已跳过 GNews 抓取")

    if not articles:
        print("[警告] 未获取到任何文章，跳过本次推送", file=sys.stderr)
        return

    print("正在获取实时行情...")
    stock_section = fetch_stock_prices(market_now_str)
    print(stock_section)
    print()

    catalyst_ref     = as_of or datetime.now(jst)
    catalyst_section = fetch_catalyst_section(catalyst_ref)
    if catalyst_section:
        print(catalyst_section)
        print()

    print(f"\n合计 {len(articles)} 条原始新闻，正在用 AI 整理...\n")
    news_section = dedup_sections(
        summarize_with_groq(articles, now_str, stock_section=stock_section)
    )

    blocks = [stock_section]
    if catalyst_section:
        blocks.append(catalyst_section)
    blocks.append(news_section)
    result = "\n\n---\n\n".join(blocks)

    print(news_section)
    print()

    send_key = os.environ.get("SERVERCHAN_KEY")
    if send_key:
        ok = push_wechat(result, send_key, as_of=as_of)
        print("[微信推送] ✓ 成功" if ok else "[微信推送] ✗ 失败，请检查 SERVERCHAN_KEY 是否正确")
    else:
        print("[提示] 未设置 SERVERCHAN_KEY，已跳过微信推送")


if __name__ == "__main__":
    main()
