#!/usr/bin/env python3
"""論文自動読み取りツール - 検索・取得・整理を自動化"""

import sys
import os
import re
import io
import json
import argparse
import threading
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime
from urllib.parse import urljoin
from concurrent.futures import ThreadPoolExecutor, as_completed

import anthropic
import requests
import fitz  # PyMuPDF
import yaml
from bs4 import BeautifulSoup

OUTPUT_MD        = Path(__file__).parent / "papers.md"
OUTPUT_JSON      = Path(__file__).parent / "papers.json"
INTERESTS_CONFIG = Path(__file__).parent / "research_interests.yaml"
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from vault_paths import vault_path

OBSIDIAN_VAULT    = vault_path("VAULT_ROOT")
OBSIDIAN_PAPERS   = vault_path("VAULT_PAPERS")
OBSIDIAN_CONCEPTS = vault_path("VAULT_CONCEPTS")

MAX_CHARS         = 80_000
HEAD_CHARS        = 35_000
TAIL_CHARS        = 35_000
MAX_RECENT_PAPERS = 30
MAX_WORKERS       = 3

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# ============================================================
# 設定ファイル読み込み
# ============================================================

def _load_config() -> dict:
    if INTERESTS_CONFIG.exists():
        try:
            with open(INTERESTS_CONFIG, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception:
            pass
    return {}

_CONFIG = _load_config()
_INTEREST_KEYWORDS: list[str] = _CONFIG.get("interests", [
    "日本語教育", "第二言語習得", "認知言語学", "日本語学",
    "関連性理論", "ファミリー・ランゲージ・ポリシー", "CLD児",
])
_EXCLUDED_KEYWORDS: list[str] = _CONFIG.get("excluded_keywords", [])
RESEARCH_INTERESTS = "、".join(_INTEREST_KEYWORDS)

SECTION_LABELS = [
    ("section_1", "研究背景"),
    ("section_2", "先行研究"),
    ("section_3", "研究課題・研究目的"),
    ("section_4", "研究方法"),
    ("section_5", "調査結果"),
    ("section_6", "考察"),
    ("section_7", "今後の課題"),
]

# ============================================================
# Claude SDK 設定
# ============================================================

_anthropic_client: anthropic.Anthropic | None = None

def _get_client() -> anthropic.Anthropic:
    global _anthropic_client
    if _anthropic_client is None:
        _anthropic_client = anthropic.Anthropic()
    return _anthropic_client


ANALYSIS_TOOL = {
    "name": "save_analysis",
    "description": "論文の分析結果を構造化データとして保存する",
    "input_schema": {
        "type": "object",
        "properties": {
            "title":     {"type": "string", "description": "論文タイトル原文"},
            "authors":   {"type": "string", "description": "著者名"},
            "year":      {"type": "string", "description": "発行年（4桁）"},
            "abstract":  {"type": "string", "description": "摘要の原文"},
            "section_1": {"type": "string", "description": "研究背景"},
            "section_2": {"type": "string", "description": "先行研究"},
            "section_3": {"type": "string", "description": "研究課題・研究目的"},
            "section_4": {"type": "string", "description": "研究方法"},
            "section_5": {"type": "string", "description": "調査結果"},
            "section_6": {"type": "string", "description": "考察"},
            "section_7": {"type": "string", "description": "今後の課題"},
            "review_good": {"type": "string", "description": "優れた点・独創性・貢献の客観的評価"},
            "review_bad":  {"type": "string", "description": "限界・改善点・不足点の客観的評価"},
            "relevance": {
                "type": "object",
                "properties": {
                    "level":  {"type": "string", "enum": ["high", "medium", "low"]},
                    "reason": {"type": "string"},
                },
                "required": ["level", "reason"],
            },
            "related_papers": {"type": "array", "items": {"type": "string"}},
            "concepts":       {"type": "array", "items": {"type": "string"}},
        },
        "required": [
            "title", "authors", "year", "abstract",
            "section_1", "section_2", "section_3", "section_4",
            "section_5", "section_6", "section_7",
            "review_good", "review_bad", "relevance",
            "related_papers", "concepts",
        ],
    },
}

CONCEPTS_TOOL = {
    "name": "save_concepts",
    "description": "抽出した研究概念リストを保存する",
    "input_schema": {
        "type": "object",
        "properties": {
            "concepts": {
                "type": "array",
                "items": {"type": "string"},
                "description": "5〜8個の研究概念・キーワード（日本語の名詞句）",
            }
        },
        "required": ["concepts"],
    },
}

# システムプロンプトはモジュール読み込み時に1度だけ構築（キャッシュ効率最大化）
ANALYSIS_SYSTEM_PROMPT = f"""\
あなたは学術論文分析の専門家です。論文テキストを分析し、save_analysis ツールを使って結果を出力してください。

【研究者の専門領域】
この分析は以下の研究領域を専門とする研究者のために行います：
{RESEARCH_INTERESTS}
relevance フィールドでは、上記の専門領域との具体的な関連性を評価してください。

【抽出ルール】
各セクション（研究背景〜今後の課題）について：
- 論文内にそのセクションを直接表す文章がある場合 → 原文をそのまま引用し「」で囲む
- 見つからない場合 → 内容を概括し、末尾に（概括）と付記する

related_papers は既読論文リストの中から本論文と関連するものを選んでタイトルをそのまま記載してください。\
関連がない場合は空配列 [] にしてください。

concepts は論文が扱う主要な研究概念・キーワードを5〜8個抽出してください。\
理論的枠組み（例：ファミリー・ランゲージ・ポリシー）、研究対象（例：CLD児）、\
研究手法（例：縦断研究、半構造化インタビュー）、主要な現象（例：継承語減衰）など。\
日本語で、名詞または短い名詞句で記載してください。\
"""

CONCEPTS_SYSTEM_PROMPT = """\
あなたは学術論文の概念抽出の専門家です。与えられた論文情報から主要な研究概念を抽出し、\
save_concepts ツールで出力してください。
概念の選び方：理論的枠組み、研究対象の特徴、研究手法、主要な現象・結果。日本語の名詞句で5〜8個。
"""

FILTER_TOOL = {
    "name": "filter_papers",
    "description": "各論文の関連度を評価する",
    "input_schema": {
        "type": "object",
        "properties": {
            "results": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "index": {"type": "integer", "description": "論文の1始まりインデックス"},
                        "level": {"type": "string", "enum": ["high", "medium", "low"], "description": "関連度"},
                    },
                    "required": ["index", "level"],
                },
            }
        },
        "required": ["results"],
    },
}

FILTER_SYSTEM_PROMPT = f"""\
あなたは学術論文の関連度評価の専門家です。研究者の専門領域に対して各論文の関連度を評価し、\
filter_papers ツールで結果を返してください。

【研究者の専門領域】
{RESEARCH_INTERESTS}

評価基準:
- high: 専門領域と直接関連（研究対象・理論枠組み・手法が一致）
- medium: 周辺領域または部分的に関連
- low: 関連性が低い・別分野
"""


# ============================================================
# 検索機能
# ============================================================

def search_cinii(query: str, count: int) -> list[dict]:
    """CiNii Research で論文を検索"""
    url = "https://cir.nii.ac.jp/opensearch/articles"
    params = {"q": query, "count": count, "format": "json", "lang": "ja"}
    try:
        r = requests.get(url, params=params, headers=REQUEST_HEADERS, timeout=15)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f"  [CiNii] 検索エラー: {e}")
        return []

    results = []
    for item in data.get("items", []):
        title = item.get("dc:title", "") or item.get("title", "")
        link = item.get("@id", "") or item.get("link", "")
        creators = item.get("dc:creator", [])
        if isinstance(creators, list):
            authors = ", ".join(
                c.get("@value", c) if isinstance(c, dict) else str(c)
                for c in creators
            )
        else:
            authors = str(creators)
        year = (item.get("prism:publicationDate", "") or "")[:4]
        if title and link:
            results.append({
                "source": "CiNii",
                "title": title,
                "url": link,
                "authors": authors,
                "year": year,
                "pdf_url": None,
                "citation_count": 0,
            })
    return results


def search_jstage(query: str, count: int) -> list[dict]:
    """J-STAGE で論文を検索（OpenSearch/Atom XML）"""
    url = "https://api.jstage.jst.go.jp/searchapi/do"
    params = {"service": 3, "keyword": query, "count": count, "lang": 1}
    try:
        r = requests.get(url, params=params, headers=REQUEST_HEADERS, timeout=15)
        r.raise_for_status()
        root = ET.fromstring(r.content)
    except Exception as e:
        print(f"  [J-STAGE] 検索エラー: {e}")
        return []

    ns = {
        "atom": "http://www.w3.org/2005/Atom",
        "prism": "http://prismstandard.org/namespaces/basic/2.0/",
        "opensearch": "http://a9.com/-/spec/opensearch/1.1/",
    }
    results = []
    for entry in root.findall("atom:entry", ns):
        title = (entry.findtext("atom:title", namespaces=ns) or "").strip()
        link_el = entry.find("atom:link[@rel='alternate']", ns) or entry.find("atom:link", ns)
        url_val = link_el.get("href", "") if link_el is not None else ""
        pdf_el = entry.find("atom:link[@type='application/pdf']", ns)
        pdf_url = pdf_el.get("href", "") if pdf_el is not None else None
        authors = ", ".join(
            (a.findtext("atom:name", namespaces=ns) or "").strip()
            for a in entry.findall("atom:author", ns)
        )
        year = (entry.findtext("prism:publicationDate", namespaces=ns) or "")[:4]
        if title and url_val:
            results.append({
                "source": "J-STAGE",
                "title": title,
                "url": url_val,
                "authors": authors,
                "year": year,
                "pdf_url": pdf_url or None,
                "citation_count": 0,
            })
    return results


def search_semantic_scholar(query: str, count: int) -> list[dict]:
    """Semantic Scholar で英語論文を検索（引用数付き）"""
    import time
    url = "https://api.semanticscholar.org/graph/v1/paper/search"
    params = {
        "query": query,
        "limit": count,
        "fields": "title,authors,year,openAccessPdf,url,citationCount",
    }
    for attempt in range(3):
        try:
            r = requests.get(url, params=params, headers=REQUEST_HEADERS, timeout=15)
            if r.status_code == 429:
                wait = 10 * (attempt + 1)
                print(f"  [Semantic Scholar] レートリミット、{wait}秒待機中...")
                time.sleep(wait)
                continue
            r.raise_for_status()
            data = r.json()
            break
        except Exception as e:
            print(f"  [Semantic Scholar] 検索エラー: {e}")
            return []
    else:
        print("  [Semantic Scholar] リトライ上限に達しました")
        return []

    results = []
    for paper in data.get("data", []):
        title = paper.get("title", "")
        authors = ", ".join(a.get("name", "") for a in paper.get("authors", []))
        year = str(paper.get("year", "") or "")
        page_url = paper.get("url", "")
        pdf_info = paper.get("openAccessPdf") or {}
        pdf_url = pdf_info.get("url") or None
        if title and page_url:
            results.append({
                "source": "Semantic Scholar",
                "title": title,
                "url": page_url,
                "authors": authors,
                "year": year,
                "pdf_url": pdf_url,
                "citation_count": paper.get("citationCount", 0) or 0,
            })
    return results


def _normalize_title(title: str) -> str:
    """重複検出用タイトル正規化"""
    normalized = re.sub(r'[^\w\s]', '', title.lower())
    return re.sub(r'\s+', ' ', normalized).strip()


def _score_paper(paper: dict) -> float:
    """キーワード適合度・引用数・新しさで論文をスコアリング"""
    score = 0.0
    text = (paper.get("title", "") + " " + (paper.get("abstract", "") or "")).lower()

    # キーワード適合度 (50%)
    matches = sum(1 for kw in _INTEREST_KEYWORDS if kw.lower() in text)
    kw_score = min(matches / max(len(_INTEREST_KEYWORDS), 1), 1.0)
    score += kw_score * 0.5

    # 引用数 (30%) — 100件で上限
    citations = paper.get("citation_count", 0) or 0
    score += min(citations / 100, 1.0) * 0.3

    # 新しさ (20%) — 20年で線形減衰
    try:
        age = max(0, 2026 - int(paper.get("year", 0) or 0))
        score += max(0.0, 1.0 - age / 20) * 0.2
    except (ValueError, TypeError):
        pass

    return score


def _filter_excluded(results: list[dict]) -> list[dict]:
    """除外キーワードを含む論文をフィルタリング"""
    if not _EXCLUDED_KEYWORDS:
        return results
    return [
        p for p in results
        if not any(ex.lower() in (p.get("title", "") or "").lower() for ex in _EXCLUDED_KEYWORDS)
    ]


def search_papers(query: str, count: int, platforms: list[str]) -> list[dict]:
    """指定プラットフォームで検索し、重複除去・フィルタリング・スコアソートして返す"""
    all_results = []
    per = max(count, 5)
    if "cinii" in platforms:
        print("  CiNii を検索中...")
        all_results += search_cinii(query, per)
    if "jstage" in platforms:
        print("  J-STAGE を検索中...")
        all_results += search_jstage(query, per)
    if "ss" in platforms:
        print("  Semantic Scholar を検索中...")
        all_results += search_semantic_scholar(query, per)

    # タイトル正規化による重複除去（同一論文が複数プラットフォームに存在する場合）
    seen: set[str] = set()
    deduped = []
    for p in all_results:
        key = _normalize_title(p.get("title", ""))
        if key and key not in seen:
            seen.add(key)
            deduped.append(p)

    filtered = _filter_excluded(deduped)

    for p in filtered:
        p["_score"] = _score_paper(p)
    filtered.sort(key=lambda p: p["_score"], reverse=True)

    return filtered


# ============================================================
# AI フィルタリング
# ============================================================

def ai_filter(results: list[dict]) -> list[dict]:
    """Claude で関連度を評価し high/medium のみ返す。失敗時は全件返す。"""
    if not results:
        return []

    src_map = {"CiNii": "C", "J-STAGE": "J", "Semantic Scholar": "S"}
    lines = []
    for i, p in enumerate(results, 1):
        src = src_map.get(p["source"], "?")
        authors = (p.get("authors") or "")[:30]
        lines.append(f"{i}. [{src}] {p['title']} ({authors}, {p.get('year', '')})")

    user_content = "以下の論文の関連度を評価してください:\n\n" + "\n".join(lines)

    print(f"  AI が {len(results)} 件を評価中...")
    try:
        response = _get_client().messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            system=[{"type": "text", "text": FILTER_SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user_content}],
            tools=[FILTER_TOOL],
            tool_choice={"type": "any"},
        )
    except Exception as e:
        print(f"  [AI フィルタ] エラー: {e} — 全件表示にフォールバック")
        return results

    level_map: dict[int, str] = {}
    for block in response.content:
        if block.type == "tool_use" and block.name == "filter_papers":
            for item in block.input.get("results", []):
                idx = item.get("index")
                lvl = item.get("level")
                if idx and lvl:
                    level_map[idx] = lvl

    filtered = []
    for i, p in enumerate(results, 1):
        lvl = level_map.get(i, "medium")
        if lvl in ("high", "medium"):
            p["_ai_level"] = lvl
            filtered.append(p)

    return filtered


# ============================================================
# 確認 UI
# ============================================================

def show_and_confirm(results: list[dict]) -> list[dict]:
    """論文一覧を表示して処理対象を選ばせる"""
    if not results:
        print("論文が見つかりませんでした。")
        return []

    src_map = {"CiNii": "C", "J-STAGE": "J", "Semantic Scholar": "S"}
    has_ai = any("_ai_level" in p for p in results)

    if has_ai:
        high = [p for p in results if p.get("_ai_level") == "high"]
        medium = [p for p in results if p.get("_ai_level") == "medium"]
        results = high + medium

    print(f"\n{'='*60}")
    print(f"  見つかった論文: {len(results)} 件")
    print(f"{'='*60}")

    if has_ai:
        counter = 1
        for label, group in [("高関連", high), ("中関連", medium)]:
            if not group:
                continue
            print(f"\n── {label} ({len(group)}件) ──")
            for p in group:
                title = p["title"][:58] + ("…" if len(p["title"]) > 58 else "")
                authors = (p["authors"] or "著者不明")[:30]
                year = p["year"] or "年不明"
                pdf_mark = " [PDF有]" if p.get("pdf_url") else ""
                src = src_map.get(p["source"], "?")
                print(f"  {counter:2}. [{src}] {title}{pdf_mark}")
                print(f"      {authors} ({year})")
                counter += 1
    else:
        for i, p in enumerate(results, 1):
            title = p["title"][:58] + ("…" if len(p["title"]) > 58 else "")
            authors = (p["authors"] or "著者不明")[:30]
            year = p["year"] or "年不明"
            pdf_mark = " [PDF有]" if p.get("pdf_url") else ""
            score = p.get("_score", 0.0)
            citations = p.get("citation_count", 0) or 0
            cite_str = f" 引用{citations}" if citations > 0 else ""
            src = src_map.get(p["source"], "?")
            print(f"  {i:2}. [{src}] {title}{pdf_mark}")
            print(f"      {authors} ({year}){cite_str}  スコア:{score:.2f}")

    print(f"\n{'='*60}")
    print("処理する論文を選択してください:")
    print("  all       - 全件処理")
    print("  1,3,5     - 番号指定（カンマ区切り）")
    print("  1-5       - 範囲指定")
    print("  none / q  - キャンセル")
    print(f"{'='*60}")

    while True:
        try:
            choice = input("> ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return []

        if choice in ("none", "q", ""):
            return []
        if choice == "all":
            return results

        selected = []
        valid = True
        for part in choice.split(","):
            part = part.strip()
            if "-" in part:
                try:
                    a, b = part.split("-", 1)
                    selected += list(range(int(a), int(b) + 1))
                except ValueError:
                    valid = False; break
            elif part.isdigit():
                selected.append(int(part))
            else:
                valid = False; break

        if not valid:
            print("入力が正しくありません。もう一度入力してください。")
            continue

        chosen = []
        for n in selected:
            if 1 <= n <= len(results):
                chosen.append(results[n - 1])
            else:
                print(f"  番号 {n} は範囲外です（スキップ）")

        if chosen:
            return chosen
        print("有効な番号を入力してください。")


# ============================================================
# PDF 取得
# ============================================================

def _fetch_bytes(url: str) -> bytes:
    r = requests.get(url, headers=REQUEST_HEADERS, timeout=60, allow_redirects=True)
    r.raise_for_status()
    return r.content


def _find_pdf_link(html: str, base_url: str) -> str | None:
    """HTML から PDF 直リンクを探す"""
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a", href=True):
        if ".pdf" in a["href"].lower():
            return urljoin(base_url, a["href"])
    for a in soup.find_all("a", href=True):
        text = (a.get_text() + a.get("aria-label", "")).lower()
        if "pdf" in text or "全文" in text or "fulltext" in text:
            return urljoin(base_url, a["href"])
    return None


def _find_repo_link(html: str, base_url: str) -> str | None:
    """CiNii 等のページから機関リポジトリ / handle.net リンクを探す"""
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "hdl.handle.net" in href:
            return href
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "auth" in href or "login" in href:
            continue
        if "機関リポジトリ" in a.get_text() or "リポジトリ" in a.get_text():
            return urljoin(base_url, href)
        if any(x in href for x in ["/repo/", "/dspace/", "repository"]) and "auth" not in href:
            return urljoin(base_url, href)
    return None


def get_pdf_bytes(source: str, pdf_url: str | None = None) -> bytes:
    """URL / ローカルパス / PDF 直リンクから PDF バイトを返す（リポジトリ2段階対応）"""
    if not (source.startswith("http://") or source.startswith("https://")):
        return Path(source).read_bytes()

    if pdf_url:
        try:
            data = _fetch_bytes(pdf_url)
            if data[:4] == b"%PDF":
                return data
        except Exception:
            pass

    r = requests.get(source, headers=REQUEST_HEADERS, timeout=30, allow_redirects=True)
    r.raise_for_status()
    content_type = r.headers.get("Content-Type", "")
    current_url = r.url

    if "pdf" in content_type.lower() or r.content[:4] == b"%PDF":
        return r.content

    pdf_link = _find_pdf_link(r.text, current_url)
    if pdf_link:
        print(f"  PDF: {pdf_link}")
        return _fetch_bytes(pdf_link)

    repo_link = _find_repo_link(r.text, current_url)
    if repo_link:
        print(f"  リポジトリ: {repo_link}")
        r2 = requests.get(repo_link, headers=REQUEST_HEADERS, timeout=30, allow_redirects=True)
        r2.raise_for_status()
        if r2.content[:4] == b"%PDF":
            return r2.content
        pdf_link2 = _find_pdf_link(r2.text, r2.url)
        if pdf_link2:
            print(f"  PDF: {pdf_link2}")
            return _fetch_bytes(pdf_link2)

    raise ValueError("PDF リンクが見つかりませんでした")


# ============================================================
# テキスト抽出（スマート截断 + スキャンPDF OCRフォールバック）
# ============================================================

OCR_MIN_CHARS = 100  # これ以下ならスキャンPDFと判断してOCRにフォールバック


def _ocr_with_claude(pdf_bytes: bytes) -> str:
    """スキャンPDFを Claude vision でOCR（ANTHROPIC_API_KEY 必須）"""
    import base64
    doc = fitz.open(stream=io.BytesIO(pdf_bytes), filetype="pdf")
    content: list[dict] = []
    for i, page in enumerate(doc):
        mat = fitz.Matrix(2.0, 2.0)
        pix = page.get_pixmap(matrix=mat)
        b64 = base64.standard_b64encode(pix.tobytes("png")).decode("utf-8")
        content.append({"type": "text", "text": f"--- ページ {i + 1} ---"})
        content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": "image/png", "data": b64},
        })
    doc.close()
    content.append({
        "type": "text",
        "text": (
            "上記全ページの日本語テキストを完全にOCRしてください。"
            "論文のタイトル・著者・発行年・摘要・本文を正確に書き起こしてください。"
            "ページ区切りは [Page N] で示してください。"
        ),
    })
    response = _get_client().messages.create(
        model="claude-sonnet-4-6",
        max_tokens=8192,
        messages=[{"role": "user", "content": content}],
    )
    return response.content[0].text


def extract_text(pdf_bytes: bytes) -> str:
    doc = fitz.open(stream=io.BytesIO(pdf_bytes), filetype="pdf")
    pages = [page.get_text() for page in doc]
    doc.close()
    full = "\n".join(pages)

    if len(full) < OCR_MIN_CHARS:
        print("  スキャンPDFを検出 — Claude OCR にフォールバックします...")
        full = _ocr_with_claude(pdf_bytes)

    if len(full) <= MAX_CHARS:
        return full

    head = full[:HEAD_CHARS]
    tail = full[-TAIL_CHARS:]
    return f"{head}\n\n[... 中略（本文中部省略）...]\n\n{tail}"


# ============================================================
# JSON データベース
# ============================================================

_db_lock = threading.Lock()


def _load_db_raw() -> dict:
    """ロックなしで JSON を読む（必ず _db_lock 保持下で呼ぶこと）"""
    if not OUTPUT_JSON.exists():
        return {"papers": []}
    try:
        return json.loads(OUTPUT_JSON.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"papers": []}


def is_already_registered(source: str) -> bool:
    with _db_lock:
        db = _load_db_raw()
        return any(p.get("source") == source for p in db["papers"])


def load_recent_papers(n: int = MAX_RECENT_PAPERS) -> list[dict]:
    with _db_lock:
        db = _load_db_raw()
    papers = sorted(db["papers"], key=lambda p: p.get("added_at", ""), reverse=True)
    return papers[:n]


# ============================================================
# Claude 分析（Anthropic SDK + tool_use + prompt caching）
# ============================================================

def _format_existing_context(papers: list[dict]) -> str:
    if not papers:
        return ""
    lines = ["【既読論文リスト（関連論文の特定に使用）】"]
    for p in papers:
        abstract_preview = (p.get("abstract") or "")[:200]
        lines.append(f"- {p.get('title', '')}（{p.get('year', '')}）: {abstract_preview}...")
    return "\n".join(lines) + "\n\n"


def analyze(text: str) -> dict:
    existing = load_recent_papers()
    user_content = _format_existing_context(existing) + "【論文テキスト】\n" + text

    response = _get_client().messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system=[{
            "type": "text",
            "text": ANALYSIS_SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"},
        }],
        messages=[{"role": "user", "content": user_content}],
        tools=[ANALYSIS_TOOL],
        tool_choice={"type": "any"},
    )

    for block in response.content:
        if block.type == "tool_use" and block.name == "save_analysis":
            return block.input

    raise RuntimeError(f"save_analysis ツールが呼ばれませんでした: {response.stop_reason}")


# ============================================================
# 保存（JSON + Markdown 同期）
# ============================================================

def _sanitize_inline(text: str) -> str:
    """テーブルセル用：改行・パイプ・区切り線を除去して1行に収める"""
    text = re.sub(r"\n+", " ", text)
    text = re.sub(r"\s*---+\s*", " ", text)
    text = text.replace("|", "｜")
    return text.strip()


def _build_md_entry(data: dict) -> str:
    title = _sanitize_inline(data.get("title", "（タイトル不明）"))
    relevance = data.get("relevance", {})
    rel_level = relevance.get("level", "—")
    rel_reason = _sanitize_inline(relevance.get("reason", "—"))
    related = data.get("related_papers", [])
    related_str = _sanitize_inline("、".join(related)) if related else "—"

    lines = [
        "\n---\n",
        f"## {title}\n",
        "| 項目 | 内容 |",
        "|------|------|",
        f"| **著者** | {_sanitize_inline(data.get('authors', '不明'))} |",
        f"| **年** | {_sanitize_inline(data.get('year', '不明'))} |",
        f"| **ソース** | {data.get('source', '—')} |",
        f"| **読み取り日** | {data.get('added_at', '—')} |",
        f"| **関連度** | {rel_level} — {rel_reason} |",
        f"| **関連既読論文** | {related_str} |",
        "",
        "### 摘要",
        "",
        data.get("abstract", "（摘要なし）"),
        "",
    ]

    for key, label in SECTION_LABELS:
        lines += [f"### {label}", "", data.get(key, "（情報なし）"), ""]

    lines += [
        "### 客観的感想",
        "",
        "**良い点**",
        "",
        data.get("review_good", "（評価なし）"),
        "",
        "**改善点・不足点**",
        "",
        data.get("review_bad", "（評価なし）"),
        "",
    ]
    return "\n".join(lines)


def extract_concepts_from_data(data: dict) -> list[str]:
    """既存の分析データから概念を抽出（PDF 再取得不要）"""
    user_content = (
        f"タイトル: {data.get('title', '')}\n"
        f"摘要: {(data.get('abstract') or '')[:500]}\n"
        f"研究背景: {(data.get('section_1') or '')[:500]}\n"
        f"考察: {(data.get('section_6') or '')[:500]}\n"
    )
    response = _get_client().messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=512,
        system=CONCEPTS_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
        tools=[CONCEPTS_TOOL],
        tool_choice={"type": "any"},
    )
    for block in response.content:
        if block.type == "tool_use" and block.name == "save_concepts":
            concepts = block.input.get("concepts", [])
            return [c for c in concepts if isinstance(c, str) and c.strip()]
    raise RuntimeError(f"save_concepts ツールが呼ばれませんでした: {response.stop_reason}")


_concept_lock = threading.Lock()


def _update_concept_note(concept: str, paper_title: str):
    """概念ノートを作成または更新して論文タイトルを追記する"""
    OBSIDIAN_CONCEPTS.mkdir(parents=True, exist_ok=True)
    path = OBSIDIAN_CONCEPTS / (_safe_filename(concept) + ".md")

    with _concept_lock:
        if path.exists():
            content = path.read_text(encoding="utf-8")
            link = f"- [[{paper_title}]]"
            if link in content:
                return
            content = content.rstrip() + f"\n{link}\n"
        else:
            content = (
                f"---\ntype: concept\ntags:\n  - 概念\n---\n\n"
                f"# {concept}\n\n## この概念を扱う論文\n\n"
                f"- [[{paper_title}]]\n"
            )
        path.write_text(content, encoding="utf-8")


def _safe_filename(title: str) -> str:
    """タイトルをファイル名として使える文字列に変換"""
    name = re.sub(r'[\\/:*?"<>|]', "_", title)
    name = re.sub(r"\s+", " ", name).strip()
    return name[:120]


def _build_obsidian_note(data: dict) -> str:
    title = data.get("title", "（タイトル不明）")
    authors = data.get("authors", "不明")
    year = data.get("year", "不明")
    source = data.get("source", "")
    platform = data.get("platform", "不明")
    added_at = data.get("added_at", "—")
    relevance = data.get("relevance", {})
    rel_level = relevance.get("level", "unknown")
    rel_reason = relevance.get("reason", "")
    related = data.get("related_papers", [])
    concepts = data.get("concepts", [])

    related_links = "\n".join(f"- {p}" for p in related) if related else "（なし）"
    concept_links = "  ".join(f"[[{c}]]" for c in concepts) if concepts else "（なし）"

    concept_tags = "\n".join(f"  - {c}" for c in concepts)
    frontmatter = f"""\
---
title: "{title.replace('"', "'")}"
authors: "{authors.replace('"', "'")}"
year: "{year}"
source: "{source}"
platform: "{platform}"
added: "{added_at}"
relevance: {rel_level}
tags:
  - 論文
  - FLP
{concept_tags}
---
"""

    body = f"""\
# {title}

> **著者**: {authors}　**年**: {year}　**関連度**: {rel_level}
> {rel_reason}
> [原文リンク]({source})

## 摘要

{data.get("abstract", "（摘要なし）")}

## 研究背景

{data.get("section_1", "（情報なし）")}

## 先行研究

{data.get("section_2", "（情報なし）")}

## 研究課題・研究目的

{data.get("section_3", "（情報なし）")}

## 研究方法

{data.get("section_4", "（情報なし）")}

## 調査結果

{data.get("section_5", "（情報なし）")}

## 考察

{data.get("section_6", "（情報なし）")}

## 今後の課題

{data.get("section_7", "（情報なし）")}

## 客観的感想

### 良い点

{data.get("review_good", "（評価なし）")}

### 改善点・不足点

{data.get("review_bad", "（評価なし）")}

## 関連論文

{related_links}

## 関連概念

{concept_links}
"""
    return frontmatter + body


def _refresh_concept_tags():
    """papers.json を読んで概念ノートの shared/unique タグを更新する"""
    with _db_lock:
        db = _load_db_raw()
    papers = db.get("papers", [])

    concept_to_papers: dict[str, list[tuple[str, str, str]]] = {}
    for p in papers:
        entry = (p.get("title", ""), p.get("year", ""), p.get("authors", ""))
        for c in p.get("concepts", []):
            concept_to_papers.setdefault(c, []).append(entry)

    if not concept_to_papers:
        return

    OBSIDIAN_CONCEPTS.mkdir(parents=True, exist_ok=True)
    for concept, paper_list in concept_to_papers.items():
        shared_tag = "shared-concept" if len(paper_list) > 1 else "unique-concept"
        paper_links = "\n".join(f"- [[{t}]]" for t, _, _ in paper_list)
        content = (
            f"---\ntype: concept\npaper_count: {len(paper_list)}\n"
            f"tags:\n  - 概念\n  - {shared_tag}\n---\n\n"
            f"# {concept}\n\n## この概念を扱う論文\n\n{paper_links}\n"
        )
        (OBSIDIAN_CONCEPTS / (_safe_filename(concept) + ".md")).write_text(
            content, encoding="utf-8"
        )


def save_to_obsidian(data: dict):
    OBSIDIAN_PAPERS.mkdir(parents=True, exist_ok=True)
    filename = _safe_filename(data.get("title", "untitled")) + ".md"
    note_path = OBSIDIAN_PAPERS / filename
    note_path.write_text(_build_obsidian_note(data), encoding="utf-8")

    title = data.get("title", "untitled")
    for concept in data.get("concepts", []):
        _update_concept_note(concept, title)

    _refresh_concept_tags()
    return note_path


def save_paper(data: dict, source: str, platform: str):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    data["source"] = source
    data["platform"] = platform
    data["added_at"] = now

    with _db_lock:
        db = _load_db_raw()
        db["papers"].append(data)
        OUTPUT_JSON.write_text(
            json.dumps(db, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        if not OUTPUT_MD.exists():
            OUTPUT_MD.write_text("# 論文読み取りノート\n\n", encoding="utf-8")
        with OUTPUT_MD.open("a", encoding="utf-8") as f:
            f.write(_build_md_entry(data))

    note_path = save_to_obsidian(data)
    print(f"  [Obsidian] → {note_path.name}")


# ============================================================
# 1本処理
# ============================================================

def process_one(source: str, pdf_url: str | None = None, platform: str = "不明"):
    label = source[:55]
    print(f"\n▶ {label}")
    if is_already_registered(source):
        print(f"  [{label}] スキップ: すでに登録済みです")
        return

    print(f"  [{label}] PDF を取得中...")
    pdf_bytes = get_pdf_bytes(source, pdf_url)

    print(f"  [{label}] テキストを抽出中...")
    text = extract_text(pdf_bytes)
    if not text.strip():
        raise ValueError("テキストを抽出できませんでした（スキャン PDF の可能性があります）")
    print(f"  [{label}] テキスト: {len(text):,} 文字")

    print(f"  [{label}] Claude で分析中...")
    data = analyze(text)
    save_paper(data, source, platform)
    print(f"  [{label}] ✓ 完了: {data.get('title', '（タイトル不明）')}")


# ============================================================
# main
# ============================================================

def _run_batch(items: list, source_fn, pdf_fn=None, platform_fn=None) -> int:
    ok = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(
                process_one,
                source_fn(item),
                pdf_fn(item) if pdf_fn else None,
                platform_fn(item) if platform_fn else "不明",
            ): item
            for item in items
        }
        for future in as_completed(futures):
            item = futures[future]
            try:
                future.result()
                ok += 1
            except Exception as e:
                label = source_fn(item)[:40]
                print(f"  ✗ {label}... エラー: {e}")
    return ok


def main():
    parser = argparse.ArgumentParser(
        description="論文自動読み取りツール",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使い方:
  # キーワードで自動検索 → 確認 → 読み取り
  python paper_reader.py -s "日本語教育 語彙習得" -n 10

  # URL / PDF を直接渡す
  python paper_reader.py https://cir.nii.ac.jp/crid/... paper.pdf

検索プラットフォーム（--platform で絞り込み可）:
  cinii   - CiNii Research（日本語論文）
  jstage  - J-STAGE（日本語論文）
  ss      - Semantic Scholar（英語論文）
""",
    )
    parser.add_argument("sources", nargs="*", help="URL またはローカル PDF パス")
    parser.add_argument("-s", "--search", metavar="QUERY", help="検索キーワード")
    parser.add_argument("-n", "--count", type=int, default=10, help="検索件数（デフォルト: 10）")
    parser.add_argument(
        "--platform",
        nargs="+",
        choices=["cinii", "jstage", "ss"],
        default=["cinii", "jstage", "ss"],
        help="検索するプラットフォーム（デフォルト: 全て）",
    )
    parser.add_argument(
        "--backfill",
        action="store_true",
        help="papers.json の既存論文を全て Obsidian vault に書き出す",
    )
    parser.add_argument(
        "--no-ai-filter",
        action="store_true",
        help="AI フィルタリングをスキップしてスコア順で全件表示",
    )
    args = parser.parse_args()

    if args.backfill:
        with _db_lock:
            db = _load_db_raw()
        papers = db.get("papers", [])
        if not papers:
            print("papers.json に論文が見つかりませんでした。")
            return
        updated = False
        for p in papers:
            if not p.get("concepts"):
                print(f"  概念抽出中: {p.get('title', '')[:50]}")
                try:
                    p["concepts"] = extract_concepts_from_data(p)
                    updated = True
                except Exception as e:
                    print(f"    ✗ 概念抽出エラー: {e}")
                    p["concepts"] = []
        if updated:
            with _db_lock:
                db_path = OUTPUT_JSON
                db_path.write_text(json.dumps(db, ensure_ascii=False, indent=2), encoding="utf-8")
            print("  papers.json を更新しました")
        print(f"\nObsidian へ書き出し: {len(papers)} 本")
        for p in papers:
            path = save_to_obsidian(p)
            print(f"  ✓ {path.name}")
        _refresh_concept_tags()
        print(f"\n完了: {OBSIDIAN_PAPERS}")
        print(f"概念ノート: {OBSIDIAN_CONCEPTS}")
        return

    if not args.search and not args.sources:
        parser.print_help()
        sys.exit(0)

    if args.search:
        print(f"\n🔍 検索: 「{args.search}」 (各 {args.count} 件)")
        results = search_papers(args.search, args.count, args.platform)
        if not args.no_ai_filter:
            original_count = len(results)
            results = ai_filter(results)
            print(f"  絞り込み: {original_count} 件 → {len(results)} 件")
        chosen = show_and_confirm(results)
        if not chosen:
            print("キャンセルしました。")
            return
        ok = _run_batch(
            chosen,
            source_fn=lambda p: p["url"],
            pdf_fn=lambda p: p.get("pdf_url"),
            platform_fn=lambda p: p["source"],
        )
        print(f"\n完了: {ok}/{len(chosen)} 本処理しました")

    if args.sources:
        ok = _run_batch(args.sources, source_fn=lambda s: s)
        print(f"\n完了: {ok}/{len(args.sources)} 本処理しました")

    if OUTPUT_MD.exists():
        print(f"Markdown: {OUTPUT_MD}")
    if OUTPUT_JSON.exists():
        print(f"JSON:     {OUTPUT_JSON}")


if __name__ == "__main__":
    main()
