"""Compare search efficiency:
  Control (DB)   : pre-chunked  <workspace>/docs/                (Layout D simulation)
  Experiment (MD): single file  <workspace>/IMX8MPRM.md          (whole-file grep)

Same 15 queries as bench_d_v2.py.
Metric per query: bytes loaded, regex matches, wall-clock ms.

Usage:
    python3 bench_md_vs_db.py [--workspace <dir>] [--md <md-file>] [--docs <docs-dir>]

Default workspace: 3 levels up from this script.
"""
import argparse
import os
import re
import sys
import time
from pathlib import Path

DEFAULT_WORKSPACE = Path(__file__).resolve().parents[3]

_p = argparse.ArgumentParser(description=__doc__)
_p.add_argument("--workspace", type=Path, default=DEFAULT_WORKSPACE,
                help=f"workspace root (default: {DEFAULT_WORKSPACE})")
_p.add_argument("--docs", type=Path, default=None,
                help="docs directory (default: <workspace>/docs)")
_p.add_argument("--md", type=Path, default=None,
                help="single MD file to grep (default: <workspace>/IMX8MPRM.md)")
_args = _p.parse_args()

DOCS_DIR = str(_args.docs if _args.docs else _args.workspace / "docs")
TOPICS_DIR = os.path.join(DOCS_DIR, "topics")
MD_FILE = str(_args.md if _args.md else _args.workspace / "IMX8MPRM.md")

QUERIES = ["HDMI", "GPU", "LCDIF", "I2C", "MIPI", "DMA", "CSI",
           "ECSPI", "VPU", "USB", "SAI", "CAAM", "USDHC", "ENET", "GPT"]


def _load_categories() -> dict:
    """Load the CATEGORIES dict directly from parse_datasheet.py.

    Avoids the bench falling out of sync with the parser whenever someone
    re-tunes the keyword groups.
    """
    parser_py = Path(__file__).resolve().parents[1] / "parse_datasheet.py"
    ns: dict = {}
    src = parser_py.read_text(encoding="utf-8")
    # Execute only the CATEGORIES literal block to avoid running side-effects.
    # The dict starts at "CATEGORIES = {" and is balanced by braces.
    start = src.index("CATEGORIES = {")
    depth = 0
    end = start
    for i in range(start, len(src)):
        c = src[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    exec(src[start:end], ns)  # noqa: S102 -- trusted local source
    return ns["CATEGORIES"]


CATEGORIES = _load_categories()


def grep_count(buf: bytes, pattern: str) -> int:
    pat = re.compile(re.escape(pattern).encode(), re.IGNORECASE)
    return sum(1 for _ in pat.finditer(buf))


# ---------- Experiment: single MD file ----------
print(f"Loading MD baseline: {MD_FILE}")
with open(MD_FILE, "rb") as f:
    MD_DATA = f.read()
MD_BYTES = len(MD_DATA)
print(f"  size: {MD_BYTES:,} bytes ({MD_BYTES/1024/1024:.1f} MB)\n")


def bench_md(query: str) -> dict:
    t0 = time.perf_counter()
    hits = grep_count(MD_DATA, query)
    dt = (time.perf_counter() - t0) * 1000
    return {"bytes": MD_BYTES, "ms": dt, "hits": hits}


# ---------- Control: pre-chunked Layout D ----------
def bench_db(query: str) -> dict:
    t0 = time.perf_counter()
    main_path = os.path.join(TOPICS_DIR, "main.md")
    with open(main_path, "rb") as f:
        main = f.read()
    bytes_total = len(main)

    q = query.lower()
    cats_to_load = set()
    for cat, kws in CATEGORIES.items():
        for kw in kws:
            kw_clean = kw.strip().lower()
            if kw_clean and (kw_clean in q or q in kw_clean):
                cats_to_load.add(cat)
                break

    if not cats_to_load:
        cats_to_load = {f.replace(".md", "") for f in os.listdir(TOPICS_DIR)
                        if f.endswith(".md") and f != "main.md"}

    hits_in_topic = 0
    sub_files: set = set()
    for cat in cats_to_load:
        path = os.path.join(TOPICS_DIR, f"{cat}.md")
        if not os.path.exists(path):
            continue
        with open(path, "rb") as f:
            data = f.read()
        bytes_total += len(data)
        hits_in_topic += grep_count(data, query)

        # Each topic file lists  "- Title (sec) -> subsystems/<file>.md"
        for m in re.finditer(rb"->\s*subsystems/([^\s)]+\.md)", data):
            sub_files.add(m.group(1).decode())

    # Now open the actual subsystem .md files referenced by those topic
    # entries that contain the keyword on the entry line. To keep parity
    # with how an agent would behave, load every subsystem file that the
    # selected topic(s) point to.
    sub_dir = os.path.join(DOCS_DIR, "subsystems")
    hits_in_sub = 0
    for fn in sub_files:
        p = os.path.join(sub_dir, fn)
        if not os.path.exists(p):
            continue
        with open(p, "rb") as f:
            d = f.read()
        bytes_total += len(d)
        hits_in_sub += grep_count(d, query)

    dt = (time.perf_counter() - t0) * 1000
    return {
        "bytes": bytes_total,
        "ms": dt,
        "hits": hits_in_topic + hits_in_sub,
        "cats": len(cats_to_load),
        "sub_files": len(sub_files),
    }


# ---------- Print table ----------
hdr = (f"{'Query':<8} | "
       f"{'DB bytes':>10} {'DB ms':>7} {'DB hits':>8} {'cats':>5} {'subs':>5} | "
       f"{'MD bytes':>10} {'MD ms':>7} {'MD hits':>8}")
print(hdr)
print("-" * len(hdr))

sum_db_b = sum_md_b = sum_db_h = sum_md_h = 0
sum_db_ms = sum_md_ms = 0.0

for q in QUERIES:
    db = bench_db(q)
    md = bench_md(q)
    sum_db_b += db["bytes"]; sum_md_b += md["bytes"]
    sum_db_h += db["hits"];  sum_md_h += md["hits"]
    sum_db_ms += db["ms"];   sum_md_ms += md["ms"]
    print(f"{q:<8} | "
          f"{db['bytes']:>10,} {db['ms']:>7.2f} {db['hits']:>8} "
          f"{db['cats']:>5} {db['sub_files']:>5} | "
          f"{md['bytes']:>10,} {md['ms']:>7.2f} {md['hits']:>8}")

print("-" * len(hdr))
print(f"{'TOTAL':<8} | "
      f"{sum_db_b:>10,} {sum_db_ms:>7.2f} {sum_db_h:>8} {'':>5} {'':>5} | "
      f"{sum_md_b:>10,} {sum_md_ms:>7.2f} {sum_md_h:>8}")

bytes_saved = sum_md_b - sum_db_b
print(f"\nBytes loaded: DB total = {sum_db_b:,}, MD total = {sum_md_b:,}")
print(f"  -> DB reads {bytes_saved/sum_md_b*100:.1f}% LESS data than MD "
      f"({bytes_saved:,} bytes saved across {len(QUERIES)} queries).")
print(f"Wall time:    DB total = {sum_db_ms:.2f} ms, MD total = {sum_md_ms:.2f} ms")
print(f"Hit recall:   DB / MD = {sum_db_h} / {sum_md_h} "
      f"= {sum_db_h/sum_md_h*100:.1f}% (DB intentionally narrows scope)")
