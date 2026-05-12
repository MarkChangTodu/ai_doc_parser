"""Fallback lookup helper for the original Markdown source.

The parser produces a chunked ``docs/`` index. When the LLM cannot find the
answer there, it should fall back to the original ``IMX8MPRM.md`` -- but it
must NEVER read the whole 15 MB file. This helper provides two minimal-token
operations the LLM can call:

  * ``grep <keyword>``  -> list of (line_no, line_text) where keyword matches
  * ``window <line>``   -> print the original lines around <line>

Source path resolution (in order):
  1. ``--md`` CLI argument
  2. ``AI_DOC_SOURCE_MD`` environment variable
  3. ``<workspace>/docs/.source`` text file (written by parse_datasheet.py)
  4. ``<workspace>/docs/source/*.md`` (single match)
  5. error

``<workspace>`` is auto-detected as 3 levels up from this script
  (fallback/ -> ai_doc_parser/ -> tools/ -> <workspace>)
or overridden via ``--workspace``.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

DEFAULT_WORKSPACE = Path(__file__).resolve().parents[3]

DEFAULT_GREP_LIMIT = 50
DEFAULT_BEFORE = 20
DEFAULT_AFTER = 100


def resolve_source_md(workspace: Path, explicit: Path | None = None) -> Path:
    if explicit:
        p = Path(explicit).expanduser().resolve()
        if not p.is_file():
            sys.exit(f"[error] --md path not found: {p}")
        return p

    env = os.environ.get("AI_DOC_SOURCE_MD")
    if env:
        p = Path(env).expanduser().resolve()
        if p.is_file():
            return p

    marker = workspace / "docs" / ".source"
    if marker.is_file():
        line = marker.read_text(encoding="utf-8").strip().splitlines()[0]
        p = Path(line).expanduser()
        if not p.is_absolute():
            p = (workspace / p).resolve()
        if p.is_file():
            return p

    src_dir = workspace / "docs" / "source"
    if src_dir.is_dir():
        cands = sorted(src_dir.glob("*.md"))
        if len(cands) == 1:
            return cands[0]
        if len(cands) > 1:
            sys.exit(f"[error] multiple .md files in {src_dir}; pick one with --md")

    sys.exit("[error] could not locate source .md "
             "(use --md, set AI_DOC_SOURCE_MD, or run parse_datasheet first)")


def cmd_grep(md_path: Path, keyword: str, limit: int, ignore_case: bool) -> int:
    flags = re.IGNORECASE if ignore_case else 0
    try:
        pat = re.compile(re.escape(keyword), flags)
    except re.error as e:
        sys.exit(f"[error] invalid pattern: {e}")

    matches: list[tuple[int, str]] = []
    with md_path.open("r", encoding="utf-8", errors="ignore") as f:
        for n, line in enumerate(f, 1):
            if pat.search(line):
                matches.append((n, line.rstrip("\n")))
                if len(matches) >= limit:
                    break

    if not matches:
        print(f"[grep] no match for {keyword!r} in {md_path}")
        return 1

    print(f"[grep] {len(matches)} match(es) for {keyword!r} in {md_path}")
    for n, text in matches:
        # Truncate very long lines to keep token usage small
        snippet = text if len(text) <= 200 else text[:200] + "..."
        print(f"  L{n:>7}: {snippet}")
    return 0


def cmd_window(md_path: Path, line: int, before: int, after: int) -> int:
    if line < 1:
        sys.exit("[error] line must be >= 1")
    start = max(1, line - before)
    end = line + after

    with md_path.open("r", encoding="utf-8", errors="ignore") as f:
        all_lines = f.readlines()

    end = min(end, len(all_lines))
    if start > len(all_lines):
        sys.exit(f"[error] line {line} > file length {len(all_lines)}")

    print(f"--- {md_path} : L{start}-L{end} (target L{line}) ---")
    width = len(str(end))
    for n in range(start, end + 1):
        marker = ">>" if n == line else "  "
        print(f"{marker} {n:>{width}}: {all_lines[n - 1].rstrip()}")
    return 0


def cmd_info(md_path: Path) -> int:
    size = md_path.stat().st_size
    with md_path.open("rb") as f:
        nlines = sum(1 for _ in f)
    print(f"path : {md_path}")
    print(f"size : {size:,} bytes ({size / 1024 / 1024:.2f} MB)")
    print(f"lines: {nlines:,}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--workspace", type=Path, default=DEFAULT_WORKSPACE,
                   help=f"workspace root (default: {DEFAULT_WORKSPACE})")
    p.add_argument("--md", type=Path, default=None,
                   help="explicit source .md path (overrides auto-resolve)")

    sub = p.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("grep", help="find lines matching a keyword")
    g.add_argument("keyword")
    g.add_argument("--limit", type=int, default=DEFAULT_GREP_LIMIT,
                   help=f"max results (default: {DEFAULT_GREP_LIMIT})")
    g.add_argument("--case-sensitive", action="store_true")

    w = sub.add_parser("window", help="print lines around a target line number")
    w.add_argument("line", type=int)
    w.add_argument("--before", type=int, default=DEFAULT_BEFORE,
                   help=f"lines to include before (default: {DEFAULT_BEFORE})")
    w.add_argument("--after", type=int, default=DEFAULT_AFTER,
                   help=f"lines to include after (default: {DEFAULT_AFTER})")

    sub.add_parser("info", help="print source .md path/size/line count")

    args = p.parse_args()
    md = resolve_source_md(args.workspace, args.md)

    if args.cmd == "grep":
        return cmd_grep(md, args.keyword, args.limit, not args.case_sensitive)
    if args.cmd == "window":
        return cmd_window(md, args.line, args.before, args.after)
    if args.cmd == "info":
        return cmd_info(md)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
