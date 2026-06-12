#!/usr/bin/env python3
"""Apple Notes ↔ Obsidian bidirectional sync.

Notes → Obsidian : HTML → Markdown，图片导出到同文件夹下的同名子目录
Obsidian → Notes : Markdown → HTML，推回 Notes
冲突策略        : Notes 优先（两边都改时，以 Notes 为准）
"""

import json
import logging
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from vault_paths import vault_path

VAULT = vault_path("VAULT_ROOT")
STATE_FILE = VAULT / ".notes_sync_state.json"

# "Claude memory" is the Claude Code persistent-memory store (symlinked from
# ~/.claude); syncing would strip its frontmatter when injecting notes_id.
SKIP_FOLDERS = {"Recently Deleted", "Trash", "Assets", "Notes", "Claude memory"}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler()],
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# System helpers
# ---------------------------------------------------------------------------

def ensure_deps():
    for pkg in ("html2text", "markdown"):
        try:
            __import__(pkg)
        except ImportError:
            subprocess.run([sys.executable, "-m", "pip", "install", pkg, "--quiet"], check=True)


def run_jxa(script: str, timeout: int = 300) -> str:
    r = subprocess.run(
        ["osascript", "-l", "JavaScript", "-e", script],
        capture_output=True, text=True, timeout=timeout,
    )
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip())
    return r.stdout.strip()


def run_as(script: str, timeout: int = 60) -> str:
    r = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True, text=True, timeout=timeout,
    )
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip())
    return r.stdout.strip()


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def safe_name(s: str) -> str:
    return re.sub(r'[/\\:*?"<>|]', "-", s).strip(". ") or "Untitled"


def now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def file_mtime_iso(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# HTML / Markdown conversion
# ---------------------------------------------------------------------------

def html_to_md(html: str) -> str:
    import html2text as _h2t
    h = _h2t.HTML2Text()
    h.body_width = 0
    h.ignore_images = False
    h.ignore_tables = False
    return h.handle(html).strip()


def md_to_html(md: str) -> str:
    import markdown as _md
    return _md.markdown(md, extensions=["tables", "fenced_code"])


# ---------------------------------------------------------------------------
# Sync state
# ---------------------------------------------------------------------------

def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"last_sync": None, "notes": {}}


def save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")


# ---------------------------------------------------------------------------
# Apple Notes access via JXA / AppleScript
# ---------------------------------------------------------------------------

_GET_NOTES_JXA = """
const app = Application('Notes');
const out = [];
for (const f of app.folders()) {
    const fn = f.name();
    for (const n of f.notes()) {
        try {
            out.push({
                id: n.id(),
                title: n.name(),
                body: n.body(),
                folder: fn,
                mtime: n.modificationDate().toISOString()
            });
        } catch(_) {}
    }
}
JSON.stringify(out);
"""


def get_apple_notes() -> list[dict]:
    log.info("Fetching all notes from Apple Notes (this may take a moment)…")
    raw = run_jxa(_GET_NOTES_JXA, timeout=300)
    notes = json.loads(raw)
    return [n for n in notes if n["folder"] not in SKIP_FOLDERS]


def save_attachments(note_id: str, dest: Path) -> list[str]:
    dest.mkdir(parents=True, exist_ok=True)
    script = f"""
tell application "Notes"
    set theNote to note id "{note_id}"
    set saved to ""
    repeat with att in attachments of theNote
        try
            save att in POSIX file "{dest}/"
            set saved to saved & name of att & linefeed
        end try
    end repeat
    saved
end tell
"""
    try:
        out = run_as(script, timeout=60)
        return [p.strip() for p in out.splitlines() if p.strip()]
    except Exception as e:
        log.warning(f"Attachment save failed for {note_id}: {e}")
        return []


def update_note_body(note_id: str, html: str):
    with tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False, encoding="utf-8") as f:
        f.write(html)
        tmp = f.name
    try:
        script = f"""
tell application "Notes"
    set c to read POSIX file "{tmp}" as «class utf8»
    set body of (note id "{note_id}") to c
end tell
"""
        run_as(script)
    finally:
        os.unlink(tmp)


def create_apple_note(folder_name: str, title: str, html: str) -> str:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False, encoding="utf-8") as f:
        f.write(html)
        tmp = f.name
    sf = folder_name.replace('"', '\\"')
    st = title.replace('"', '\\"')
    try:
        script = f"""
tell application "Notes"
    set c to read POSIX file "{tmp}" as «class utf8»
    if (count of (folders whose name is "{sf}")) > 0 then
        set dest to first folder whose name is "{sf}"
    else
        set dest to make new folder with properties {{name:"{sf}"}}
    end if
    set n to make new note at dest with properties {{name:"{st}", body:c}}
    id of n
end tell
"""
        return run_as(script).strip()
    finally:
        os.unlink(tmp)


# ---------------------------------------------------------------------------
# Obsidian file operations
# ---------------------------------------------------------------------------

_FM_RE = re.compile(r"^---\r?\n(.*?)\r?\n---\r?\n", re.DOTALL)


def read_notes_id(content: str) -> str | None:
    m = _FM_RE.match(content)
    if m:
        id_m = re.search(r"^notes_id:\s*(.+)$", m.group(1), re.MULTILINE)
        if id_m:
            return id_m.group(1).strip()
    return None


def strip_frontmatter(content: str) -> str:
    return _FM_RE.sub("", content).strip()


def write_obsidian_file(folder: str, title: str, md: str, note_id: str) -> Path:
    d = VAULT / safe_name(folder)
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{safe_name(title)}.md"
    p.write_text(f"---\nnotes_id: {note_id}\n---\n\n{md}", encoding="utf-8")
    return p


def get_obsidian_files() -> list[dict]:
    files = []
    for p in VAULT.rglob("*.md"):
        if any(part.startswith(".") for part in p.parts):
            continue
        try:
            rel = p.relative_to(VAULT)
        except ValueError:
            continue
        try:
            content = p.read_text(encoding="utf-8")
        except Exception:
            continue
        folder = rel.parent.name if len(rel.parts) > 1 else "Notes"
        files.append({
            "path": p,
            "folder": folder,
            "title": p.stem,
            "notes_id": read_notes_id(content),
            "content": content,
            "mtime": file_mtime_iso(p),
        })
    return files


# ---------------------------------------------------------------------------
# Sync: Notes → Obsidian
# ---------------------------------------------------------------------------

def sync_notes_to_obsidian(state: dict, apple_notes: list[dict]):
    log.info(f"Notes → Obsidian: {len(apple_notes)} notes to check")
    updated = 0
    for note in apple_notes:
        nid = note["id"]
        stored = state["notes"].get(nid, {})

        # Skip if Notes hasn't changed since last sync
        if stored.get("notes_mtime") == note["mtime"]:
            ob_path_str = stored.get("obsidian_path")
            if ob_path_str and Path(ob_path_str).exists():
                continue

        log.info(f"  Exporting: {note['folder']}/{note['title']}")

        # Save attachments, embed as Obsidian wikilinks
        att_dest = VAULT / safe_name(note["folder"]) / safe_name(note["title"])
        saved = save_attachments(nid, att_dest)

        md = html_to_md(note["body"])

        if saved:
            md += "\n\n---\n"
            for fname in saved:
                md += f"\n![[{fname}]]"

        ob_path = write_obsidian_file(note["folder"], note["title"], md, nid)
        updated += 1

        state["notes"][nid] = {
            "title": note["title"],
            "folder": note["folder"],
            "obsidian_path": str(ob_path),
            "notes_mtime": note["mtime"],
            "obsidian_mtime": file_mtime_iso(ob_path),
        }

    log.info(f"Notes → Obsidian: {updated} files written")


# ---------------------------------------------------------------------------
# Sync: Obsidian → Notes
# ---------------------------------------------------------------------------

def sync_obsidian_to_notes(state: dict):
    files = get_obsidian_files()
    log.info(f"Obsidian → Notes: {len(files)} files to check")

    # Folders that are already synced with Notes (safe to push new files from)
    synced_folders = {v["folder"] for v in state["notes"].values()}
    updated = 0

    for f in files:
        if f["folder"] in SKIP_FOLDERS:
            continue
        nid = f["notes_id"]
        ob_mtime = f["mtime"]

        if nid and nid in state["notes"]:
            stored = state["notes"][nid]
            ob_changed = ob_mtime > stored.get("obsidian_mtime", "")
            notes_newer = stored.get("notes_mtime", "") > stored.get("obsidian_mtime", "")

            if not ob_changed:
                continue
            if notes_newer:
                # Conflict: Notes wins — Obsidian already overwritten in previous direction
                log.info(f"  Conflict (Notes wins): {f['folder']}/{f['title']}")
                continue

            log.info(f"  Pushing: {f['folder']}/{f['title']}")
            html = md_to_html(strip_frontmatter(f["content"]))
            try:
                update_note_body(nid, html)
                stored["obsidian_mtime"] = ob_mtime
                stored["notes_mtime"] = now_iso()
                updated += 1
            except Exception as e:
                log.error(f"  Failed to push {f['title']}: {e}")

        elif not nid and f["folder"] in synced_folders:
            # New .md file in a known Notes folder → create in Notes
            log.info(f"  Creating new note: {f['folder']}/{f['title']}")
            html = md_to_html(strip_frontmatter(f["content"]))
            try:
                new_id = create_apple_note(f["folder"], f["title"], html)
                new_content = f"---\nnotes_id: {new_id}\n---\n\n{strip_frontmatter(f['content'])}"
                f["path"].write_text(new_content, encoding="utf-8")
                state["notes"][new_id] = {
                    "title": f["title"],
                    "folder": f["folder"],
                    "obsidian_path": str(f["path"]),
                    "notes_mtime": now_iso(),
                    "obsidian_mtime": file_mtime_iso(f["path"]),
                }
                updated += 1
            except Exception as e:
                log.error(f"  Failed to create {f['title']}: {e}")

    log.info(f"Obsidian → Notes: {updated} notes pushed")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    ensure_deps()
    VAULT.mkdir(parents=True, exist_ok=True)

    log.info("=== Notes ↔ Obsidian Sync Start ===")
    state = load_state()
    try:
        apple_notes = get_apple_notes()
        sync_notes_to_obsidian(state, apple_notes)
        sync_obsidian_to_notes(state)
        state["last_sync"] = now_iso()
        log.info("=== Sync Complete ===")
    except Exception as e:
        log.error(f"Sync failed: {e}", exc_info=True)
    finally:
        save_state(state)


if __name__ == "__main__":
    main()
