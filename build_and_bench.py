"""
Build three index layouts (B/C/D) and benchmark search efficiency
against the baseline single-file index (A).

Layouts:
  A (baseline): docs/subsystems_index.md  (single huge file)
  B (two-tier): docs/idx_b/main.md  + docs/idx_b/ch_NN.md
  C (per-ch)  : docs/idx_c/ch_NN.md
  D (topic)   : docs/idx_d/main.md  + docs/idx_d/<category>.md

Benchmark metric (per query keyword):
  - bytes_loaded : total bytes the agent must read to locate target file(s)
  - wall_time_ms : python read+grep time
  - hit_count    : number of section entries matched

Agent simulation per layout:
  A: load A entirely, grep
  B: load main.md, grep -> get chapter -> load that ch_NN.md, grep
     (if no chapter hit in main, fall back to scanning all sub-indexes)
  C: grep across all ch_NN.md (must read all, like a flat scan)
  D: load main.md, grep -> get category -> load <category>.md, grep
     (if no hit in main, fall back to scanning all)
"""
import os
import re
import time
import json
from collections import defaultdict

INPUT_FILE = "/home/markchang/zephyrproject/IMX8MPRM.txt"
BASE_DIR = "/home/markchang/zephyrproject/docs"

A_PATH = os.path.join(BASE_DIR, "subsystems_index.md")
B_DIR = os.path.join(BASE_DIR, "idx_b")
C_DIR = os.path.join(BASE_DIR, "idx_c")
D_DIR = os.path.join(BASE_DIR, "idx_d")

ALIAS = {
    "graphics processing unit": "gpu",
    "video processing unit": "vpu",
}

# Topic categories for layout D (keyword -> category)
CATEGORIES = {
    "display": ["lcdif", "hdmi", "mipi_dsi", "mipi dsi", "dpu", "pxp", "dcss", "display"],
    "camera":  ["csi", "mipi_csi", "mipi csi", "isp", "isi", "camera"],
    "audio":   ["sai", "asrc", "pdm", "audmix", "spdif", "mqs", "audio"],
    "security":["caam", "snvs", "ocotp", "hab", "sjc", "trustzone", "security"],
    "storage": ["usdhc", "qspi", "flexspi", "nand", "emmc", "sd"],
    "comm":    ["ecspi", "i2c", "uart", "can", "flexcan", "enet", "eqos", "pcie", "usb"],
    "gpu":     ["gpu", "gc7000", "vivante", "gc320", "graphics"],
    "vpu":     ["vpu", "hantro", "malone", "video"],
    "timer":   ["gpt", "epit", "pwm", "watchdog", "wdog"],
    "dma":     ["sdma", "edma", " dma "],
    "power":   ["ccm", "gpc", "src", "anatop", "pmu", "clock", "reset", "power"],
    "core":    ["cortex", "gic", "mmu", "a53", "m7"],
    "bus":     ["aips", "axi", "ahb", "noc", "interconnect"],
}

QUERIES = ["HDMI", "GPU", "LCDIF", "I2C", "MIPI", "DMA", "CSI",
           "ECSPI", "VPU", "USB", "SAI", "CAAM", "USDHC", "ENET", "GPT"]


def normalize(name):
    return re.sub(r'[^a-z0-9]+', '_', name.lower()).strip("_")


def get_level(section):
    return section.count(".")


def parse_sections():
    print("[parse] reading IMX8MPRM.txt ...")
    with open(INPUT_FILE, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()

    sections = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i].strip()
        m = re.match(r'^\s*Chapter\s+(\d+)\s+(.+)', line, re.IGNORECASE)
        if m:
            sections.append((m.group(1), m.group(2).strip(), i))
            i += 1
            continue
        m = re.match(r'^\s*(\d+(\.\d+)?)$', line)
        if m and i + 1 < n:
            nxt = lines[i + 1].strip()
            if len(nxt) > 5:
                sections.append((m.group(1), nxt, i))
                i += 2
                continue
        m = re.match(r'^\s*(\d+(\.\d+)?)\s+(.+)', line)
        if m:
            sections.append((m.group(1), m.group(3).strip(), i))
            i += 1
            continue
        i += 1
    print(f"[parse] {len(sections)} sections")
    return sections


def section_to_filename(title):
    name = normalize(title)
    for k, v in ALIAS.items():
        if k in title.lower():
            name = v
    return name[:60] + ".md"


def chapter_of(section):
    """Top-level chapter number, e.g. '6.5.5' -> '6'."""
    return section.split(".")[0]


# ------------- Layout B -------------
def build_b(sections):
    os.makedirs(B_DIR, exist_ok=True)
    # group by chapter
    by_ch = defaultdict(list)
    for sec, title, _ in sections:
        if get_level(sec) <= 1:
            by_ch[chapter_of(sec)].append((sec, title))

    # main: only chapter (level 0)
    main = os.path.join(B_DIR, "main.md")
    with open(main, "w") as f:
        f.write("# Subsystems Index (Layout B - main)\n\n")
        for ch in sorted(by_ch.keys(), key=lambda x: int(x)):
            # chapter title = first level-0 entry of that chapter
            ch_entries = by_ch[ch]
            ch0 = next((t for s, t in ch_entries if get_level(s) == 0), ch_entries[0][1])
            f.write(f"- Chapter {ch}: {ch0} -> idx_b/ch_{ch.zfill(2)}.md\n")

    # per-chapter sub index
    for ch, entries in by_ch.items():
        sub = os.path.join(B_DIR, f"ch_{ch.zfill(2)}.md")
        with open(sub, "w") as f:
            f.write(f"# Chapter {ch} Index\n\n")
            for sec, title in entries:
                fname = section_to_filename(title)
                f.write(f"- {title} ({sec}) -> {fname}\n")
    print(f"[B] built {len(by_ch)} chapter sub-indexes + main.md")


# ------------- Layout C -------------
def build_c(sections):
    os.makedirs(C_DIR, exist_ok=True)
    by_ch = defaultdict(list)
    for sec, title, _ in sections:
        if get_level(sec) <= 1:
            by_ch[chapter_of(sec)].append((sec, title))
    for ch, entries in by_ch.items():
        sub = os.path.join(C_DIR, f"ch_{ch.zfill(2)}.md")
        with open(sub, "w") as f:
            f.write(f"# Chapter {ch} Index\n\n")
            for sec, title in entries:
                fname = section_to_filename(title)
                f.write(f"- {title} ({sec}) -> {fname}\n")
    print(f"[C] built {len(by_ch)} chapter index files (no main)")


# ------------- Layout D -------------
def categorize(title):
    t = title.lower()
    for cat, kws in CATEGORIES.items():
        for kw in kws:
            if kw in t:
                return cat
    return "misc"


def build_d(sections):
    os.makedirs(D_DIR, exist_ok=True)
    by_cat = defaultdict(list)
    for sec, title, _ in sections:
        if get_level(sec) <= 1:
            by_cat[categorize(title)].append((sec, title))

    main = os.path.join(D_DIR, "main.md")
    with open(main, "w") as f:
        f.write("# Subsystems Index (Layout D - main, by topic)\n\n")
        for cat in sorted(by_cat.keys()):
            kws = CATEGORIES.get(cat, [cat])
            f.write(f"- **{cat}** (keywords: {', '.join(kws)}) -> idx_d/{cat}.md\n")

    for cat, entries in by_cat.items():
        sub = os.path.join(D_DIR, f"{cat}.md")
        with open(sub, "w") as f:
            f.write(f"# Category: {cat}\n\n")
            for sec, title in entries:
                fname = section_to_filename(title)
                f.write(f"- {title} ({sec}) -> {fname}\n")
    print(f"[D] built {len(by_cat)} category files + main.md")


# ------------- Benchmark -------------
def read_bytes(path):
    with open(path, "rb") as f:
        return f.read()


def grep(text_bytes, pattern):
    """Return list of line indices that match (case-insensitive)."""
    pat = re.compile(re.escape(pattern).encode(), re.IGNORECASE)
    return [i for i, ln in enumerate(text_bytes.splitlines()) if pat.search(ln)]


def bench_a(query):
    t0 = time.perf_counter()
    data = read_bytes(A_PATH)
    hits = grep(data, query)
    dt = (time.perf_counter() - t0) * 1000
    return {"bytes": len(data), "ms": dt, "hits": len(hits)}


def bench_b(query):
    t0 = time.perf_counter()
    main = read_bytes(os.path.join(B_DIR, "main.md"))
    bytes_total = len(main)
    # main only has chapter titles; if query keyword appears in any chapter title, drill into that chapter
    # otherwise, scan all sub-indexes (worst case fallback)
    main_hits = grep(main, query)
    chapters_to_load = set()
    if main_hits:
        for idx in main_hits:
            ln = main.splitlines()[idx].decode(errors="ignore")
            m = re.search(r'ch_(\d+)\.md', ln)
            if m:
                chapters_to_load.add(m.group(1))
    if not chapters_to_load:
        # fallback: scan all
        chapters_to_load = {f.split("_")[1].split(".")[0]
                            for f in os.listdir(B_DIR) if f.startswith("ch_")}
    hits = 0
    for ch in chapters_to_load:
        sub = read_bytes(os.path.join(B_DIR, f"ch_{ch}.md"))
        bytes_total += len(sub)
        hits += len(grep(sub, query))
    dt = (time.perf_counter() - t0) * 1000
    return {"bytes": bytes_total, "ms": dt, "hits": hits,
            "chapters_loaded": len(chapters_to_load)}


def bench_c(query):
    t0 = time.perf_counter()
    bytes_total = 0
    hits = 0
    files = sorted(os.listdir(C_DIR))
    for f in files:
        data = read_bytes(os.path.join(C_DIR, f))
        bytes_total += len(data)
        hits += len(grep(data, query))
    dt = (time.perf_counter() - t0) * 1000
    return {"bytes": bytes_total, "ms": dt, "hits": hits, "files_loaded": len(files)}


def bench_d(query):
    t0 = time.perf_counter()
    main = read_bytes(os.path.join(D_DIR, "main.md"))
    bytes_total = len(main)
    # find category by keyword in main
    cats_to_load = set()
    q = query.lower()
    for cat, kws in CATEGORIES.items():
        for kw in kws:
            if kw in q or q in kw:
                cats_to_load.add(cat)
    if not cats_to_load:
        cats_to_load = {f.replace(".md", "")
                        for f in os.listdir(D_DIR)
                        if f.endswith(".md") and f != "main.md"}
    hits = 0
    for cat in cats_to_load:
        path = os.path.join(D_DIR, f"{cat}.md")
        if not os.path.exists(path):
            continue
        data = read_bytes(path)
        bytes_total += len(data)
        hits += len(grep(data, query))
    dt = (time.perf_counter() - t0) * 1000
    return {"bytes": bytes_total, "ms": dt, "hits": hits,
            "cats_loaded": len(cats_to_load)}


def run_bench():
    print("\n=== BENCHMARK ===")
    rows = []
    for q in QUERIES:
        a = bench_a(q)
        b = bench_b(q)
        c = bench_c(q)
        d = bench_d(q)
        rows.append((q, a, b, c, d))

    # totals
    sums = {k: {"bytes": 0, "ms": 0.0, "hits": 0} for k in "ABCD"}
    for q, a, b, c, d in rows:
        for layout, r in zip("ABCD", (a, b, c, d)):
            sums[layout]["bytes"] += r["bytes"]
            sums[layout]["ms"] += r["ms"]
            sums[layout]["hits"] += r["hits"]

    # pretty print
    print(f"\n{'Query':<10} | {'A bytes':>9} {'A ms':>6} {'A hit':>5} | "
          f"{'B bytes':>9} {'B ms':>6} {'B hit':>5} | "
          f"{'C bytes':>9} {'C ms':>6} {'C hit':>5} | "
          f"{'D bytes':>9} {'D ms':>6} {'D hit':>5}")
    print("-" * 140)
    for q, a, b, c, d in rows:
        print(f"{q:<10} | {a['bytes']:>9} {a['ms']:>6.1f} {a['hits']:>5} | "
              f"{b['bytes']:>9} {b['ms']:>6.1f} {b['hits']:>5} | "
              f"{c['bytes']:>9} {c['ms']:>6.1f} {c['hits']:>5} | "
              f"{d['bytes']:>9} {d['ms']:>6.1f} {d['hits']:>5}")
    print("-" * 140)
    print(f"{'TOTAL':<10} | {sums['A']['bytes']:>9} {sums['A']['ms']:>6.1f} {sums['A']['hits']:>5} | "
          f"{sums['B']['bytes']:>9} {sums['B']['ms']:>6.1f} {sums['B']['hits']:>5} | "
          f"{sums['C']['bytes']:>9} {sums['C']['ms']:>6.1f} {sums['C']['hits']:>5} | "
          f"{sums['D']['bytes']:>9} {sums['D']['ms']:>6.1f} {sums['D']['hits']:>5}")

    # ranking by total bytes loaded (lower = better for LLM context)
    ranking = sorted("ABCD", key=lambda k: sums[k]["bytes"])
    print(f"\n>>> Best (least bytes loaded into context): {ranking[0]}")
    print(f">>> Ranking by bytes: {' < '.join(ranking)}")


def main():
    sections = parse_sections()
    build_b(sections)
    build_c(sections)
    build_d(sections)
    run_bench()


if __name__ == "__main__":
    main()
