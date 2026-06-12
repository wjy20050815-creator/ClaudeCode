#!/usr/bin/env python3
"""vault index/log 对账脚本 — 保持 index.md（hot cache）与 vault 实际文件一致。

--check          只报告漂移（有漂移 exit 1）
--fix            修复：按文件真实位置重组 section、删除死条目、为新文件追加条目、
                 更新计数，并在 log.md 记一笔
--reason TEXT    写进 log.md 的触发来源（如 daily_brief / notes_sync / manual）

机制说明：
- index.md 的 section 标题形如 「## `folder/`」或「## (vault root)」，条目形如 「- [[name]] — 描述」
- 条目解析：wikilink 含 "/" 时按 vault 相对路径解析，否则先按所在 section 文件夹、
  再按全库 basename 解析（与 Obsidian shortest-path 行为一致）——文件被移动后旧条目
  仍能找到家，--fix 会把它归到真实文件夹的 section 下
- 已有条目的描述原样保留；新条目描述取文件第一个标题（无标题取首行正文）
- 私密文件夹（只和自己倾诉/）只列文件名，不读内容
- 同名文件存在于多个文件夹时，新条目用相对路径 wikilink 消歧
"""

import argparse
import re
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from vault_paths import vault_path

JST = timezone(timedelta(hours=9))
PRIVATE_PREFIXES = ("只和自己倾诉",)
# 不入 index 的文件：治理基础设施自身
EXCLUDE_REL = {"index.md", "log.md"}


def list_vault_files(vault: Path) -> set[str]:
    files = set()
    for p in vault.rglob("*.md"):
        rel = p.relative_to(vault)
        if any(part.startswith(".") or part == "_attachments" for part in rel.parts):
            continue
        if str(rel) in EXCLUDE_REL:
            continue
        files.add(str(rel))
    return files


def parse_sections(index_text: str):
    """返回 (header_lines, prose_sections, sections)。

    folder section（标题为 `folder/` 或 (vault root)）按条目解析并可重组；
    其他 ## 标题（如 "## For future Claude"）是 prose section，原样保留。
    """
    lines = index_text.splitlines()
    header, prose, sections = [], [], []
    cur = None       # folder section
    cur_prose = None  # prose section 的行列表
    for line in lines:
        m = re.match(r"^## (.+)$", line)
        if m:
            title = m.group(1).strip()
            fm = re.match(r"^`(.+?)/?`$", title)
            if title == "(vault root)" or fm:
                folder = "" if title == "(vault root)" else fm.group(1).rstrip("/")
                cur = {"folder": folder, "desc": None, "entries": []}
                sections.append(cur)
                cur_prose = None
            else:
                cur = None
                cur_prose = [line]
                prose.append(cur_prose)
        elif cur is not None:
            s = line.strip()
            if s.startswith("- [["):
                cur["entries"].append(s)
            elif s.startswith("_") and s.endswith("_") and cur["desc"] is None:
                cur["desc"] = s
        elif cur_prose is not None:
            cur_prose.append(line)
        else:
            header.append(line)
    return header, prose, sections


def entry_target(line: str) -> str | None:
    m = re.match(r"^- \[\[([^\]|]+)(?:\|[^\]]*)?\]\]", line.strip())
    return m.group(1).strip() if m else None


def resolve_entry(target: str, folder: str, all_files: set[str]) -> str | None:
    """把 wikilink 解析成 vault 相对路径；找不到返回 None（死条目）"""
    candidates = []
    if "/" in target:
        candidates.append(f"{target}.md")
    candidates.append(f"{folder}/{target}.md" if folder else f"{target}.md")
    basename = target.split("/")[-1] + ".md"
    candidates.extend(f for f in sorted(all_files) if f.split("/")[-1] == basename)
    for c in candidates:
        if c in all_files:
            return c
    return None


def describe(vault: Path, rel: str) -> str:
    if rel.startswith(PRIVATE_PREFIXES):
        return ""
    try:
        text = (vault / rel).read_text(encoding="utf-8")
    except Exception:
        return ""
    body = re.sub(r"^---\n.*?\n---\n", "", text, count=1, flags=re.DOTALL)
    for line in body.splitlines():
        line = line.strip()
        if not line:
            continue
        line = re.sub(r"^#+\s*", "", line)
        line = re.sub(r"[*_`>\[\]]", "", line).strip()
        if line:
            return line[:60]
    return ""


def folder_of(rel: str) -> str:
    return str(Path(rel).parent) if "/" in rel else ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fix", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--reason", default="manual")
    args = ap.parse_args()

    vault = vault_path("VAULT_ROOT")
    index_path = vault_path("VAULT_INDEX")
    log_path = vault_path("VAULT_LOG")

    all_files = list_vault_files(vault)
    index_text = index_path.read_text(encoding="utf-8")
    header, prose, sections = parse_sections(index_text)

    # 解析所有条目：file_lines 保留首见条目行；desc 行按「section 文件夹确实存在」保留
    file_lines: dict[str, str] = {}
    file_origin: dict[str, str] = {}
    folder_order: list[str] = []
    folder_desc: dict[str, str] = {}
    dead: list[str] = []
    dup = 0
    for sec in sections:
        if sec["desc"] and (sec["folder"] == "" or (vault / sec["folder"]).is_dir()):
            folder_desc.setdefault(sec["folder"], sec["desc"])
        for line in sec["entries"]:
            target = entry_target(line)
            resolved = resolve_entry(target, sec["folder"], all_files)
            if resolved is None:
                dead.append(line)
                continue
            if resolved in file_lines:
                dup += 1
                continue
            file_lines[resolved] = line
            file_origin[resolved] = sec["folder"]
            f = folder_of(resolved)
            if f not in folder_order:
                folder_order.append(f)

    missing = sorted(all_files - set(file_lines))
    misplaced = [rel for rel, origin in file_origin.items() if folder_of(rel) != origin]

    if not missing and not dead and not dup and not misplaced:
        print("[ok] index 与 vault 一致，无漂移")
        return 0

    print(f"[drift] 缺失 {len(missing)}，死条目 {len(dead)}，重复 {dup}，错位（section 与实际文件夹不符）{len(misplaced)}")
    for f in missing:
        print(f"  + {f}")
    for line in dead:
        print(f"  - {line}")
    for f in misplaced[:10]:
        print(f"  ~ {f}")

    if not args.fix:
        return 1

    # 为缺失文件生成条目
    basename_counts = Counter(f.split("/")[-1] for f in all_files)
    for rel in missing:
        name = rel[:-3]
        link = name if basename_counts[rel.split("/")[-1]] > 1 else name.split("/")[-1]
        desc = describe(vault, rel)
        file_lines[rel] = f"- [[{link}]] — {desc}" if desc else f"- [[{link}]]"
        f = folder_of(rel)
        if f not in folder_order:
            folder_order.append(f)

    # 按真实文件夹重组输出
    by_folder: dict[str, list[str]] = {}
    for rel in file_lines:
        by_folder.setdefault(folder_of(rel), []).append(rel)

    today = datetime.now(JST).strftime("%Y-%m-%d")
    stamp = f"(vault_index_sync: +{len(missing)} −{len(dead) + dup}, 重组 {len(misplaced)})"

    def patch_counter(line: str) -> str:
        if not line.startswith("**Total notes:**"):
            return line
        line = re.sub(r"\*\*Total notes:\*\* \d+", f"**Total notes:** {len(all_files)}", line)
        if "**Last patched:**" in line:
            line = re.sub(r"\*\*Last patched:\*\* .*$", f"**Last patched:** {today} {stamp}", line)
        else:
            line += f" · **Last patched:** {today} {stamp}"
        return line

    out = [patch_counter(l) for l in header]
    for block in prose:
        out.extend(patch_counter(l) for l in block)
    while out and out[-1] == "":
        out.pop()
    out.append("")
    for folder in folder_order:
        rels = by_folder.get(folder)
        if not rels:
            continue
        out.append("## (vault root)" if folder == "" else f"## `{folder}/`")
        out.append("")
        if folder in folder_desc:
            out.append(folder_desc[folder])
            out.append("")
        # 原有条目保持首见顺序，新条目排在后面（file_lines 插入序即此序）
        out.extend(file_lines[rel] for rel in rels)
        out.append("")
    index_path.write_text("\n".join(out).rstrip("\n") + "\n", encoding="utf-8")

    sample_add = "、".join(m.split("/")[-1][:-3] for m in missing[:5]) + ("…" if len(missing) > 5 else "")
    sample_del = "、".join(entry_target(l) or "?" for l in dead[:5]) + ("…" if len(dead) > 5 else "")
    log_line = (
        f"\n## [{today}] index-sync | 来源: {args.reason}。"
        f"新增 {len(missing)} 条（{sample_add or '无'}），移除死/重复条目 {len(dead) + dup} 条（{sample_del or '无'}），"
        f"错位重组 {len(misplaced)} 条。Total notes: {len(all_files)}。\n"
    )
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(log_line)
    print(f"[fixed] index.md 已重组（+{len(missing)} −{len(dead) + dup} ~{len(misplaced)}），log.md 已记录")
    return 0


if __name__ == "__main__":
    sys.exit(main())
