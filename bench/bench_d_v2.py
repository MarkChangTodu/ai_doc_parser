"""Re-benchmark Layout D (optimized, multi-category) vs baseline A.

Usage:
    python3 bench_d_v2.py [--workspace <dir>]

Default workspace: 3 levels up from this script
    (bench/ -> ai_doc_parser/ -> tools/ -> <workspace>)
"""
import argparse
import os
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

DEFAULT_WORKSPACE = Path(__file__).resolve().parents[3]

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--workspace", type=Path, default=DEFAULT_WORKSPACE,
                    help=f"workspace root (default: {DEFAULT_WORKSPACE})")
parser.add_argument("--docs", type=Path, default=None,
                    help="docs/ directory (default: <workspace>/docs)")
args = parser.parse_args()

BASE_DIR = str(args.docs if args.docs else args.workspace / "docs")
A_PATH = os.path.join(BASE_DIR, "subsystems_index.md")  # short chapter-only version now
TOPICS_DIR = os.path.join(BASE_DIR, "topics")

if not os.path.isdir(TOPICS_DIR):
    sys.exit(f"[error] topics dir not found: {TOPICS_DIR}")
print(f"[info] using docs: {BASE_DIR}")

# Same query set as before
QUERIES = ["HDMI", "GPU", "LCDIF", "I2C", "MIPI", "DMA", "CSI",
           "ECSPI", "VPU", "USB", "SAI", "CAAM", "USDHC", "ENET", "GPT"]

# Reproduce CATEGORIES from parser to drive D simulation
CATEGORIES = {
    "display": ["lcdif", "hdmi", "mipi dsi", "mipi_dsi", "dsi", "dpu", "pxp", "dcss", "display", "lvds"],
    "camera":  ["csi", "mipi csi", "mipi_csi", "isp", "isi", "camera"],
    "audio":   ["sai", "asrc", "pdm", "audmix", "spdif", "mqs", "audio", "i2s"],
    "security":["caam", "snvs", "ocotp", "hab", "sjc", "trustzone", "security", "rdc", "csu"],
    "storage": ["usdhc", "qspi", "flexspi", "nand", "emmc", "sdmmc", " sd "],
    "comm":    ["ecspi", "i2c", "uart", "can", "flexcan", "enet", "eqos", "pcie", "usb", "spi"],
    "gpu":     ["gpu", "gc7000", "vivante", "gc320", "graphics"],
    "vpu":     ["vpu", "hantro", "malone", "video", "vc8000"],
    "timer":   ["gpt", "epit", "pwm", "watchdog", "wdog", "timer"],
    "dma":     ["sdma", "edma", " dma", "dma "],
    "power":   ["ccm", "gpc", "src", "anatop", "pmu", "clock", "reset", "power", "ldo", "regulator"],
    "core":    ["cortex", "gic", "mmu", "a53", "m7", "smmu"],
    "bus":     ["aips", "axi", "ahb", "noc", "interconnect", "bus"],
    "mipi":    ["mipi"],
    "hdmi":    ["hdmi"],
}

# Old single-file baseline path - we need to reconstruct A for fair comparison.
# The new subsystems_index.md is chapter-only (very short), so we rebuild a
# "fat A" snapshot by listing all level<=1 entries from the existing topic files
# (deduped). That equals the old A.
def build_baseline_a_in_memory():
    seen = set()
    lines = ["# Baseline A (reconstructed)\n\n"]
    for fn in os.listdir(TOPICS_DIR):
        if fn == "main.md": continue
        with open(os.path.join(TOPICS_DIR, fn)) as f:
            for ln in f:
                if ln.startswith("- ") and ln not in seen:
                    seen.add(ln)
                    lines.append(ln)
    data = "".join(lines).encode()
    return data

A_DATA = build_baseline_a_in_memory()

def grep(text_bytes, pattern):
    pat = re.compile(re.escape(pattern).encode(), re.IGNORECASE)
    return [i for i, ln in enumerate(text_bytes.splitlines()) if pat.search(ln)]

def bench_a(query):
    t0 = time.perf_counter()
    hits = grep(A_DATA, query)
    dt = (time.perf_counter() - t0) * 1000
    return {"bytes": len(A_DATA), "ms": dt, "hits": len(hits)}

def bench_d(query):
    t0 = time.perf_counter()
    with open(os.path.join(TOPICS_DIR, "main.md"), "rb") as f:
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
    hits = 0
    for cat in cats_to_load:
        path = os.path.join(TOPICS_DIR, f"{cat}.md")
        if not os.path.exists(path): continue
        with open(path, "rb") as f:
            data = f.read()
        bytes_total += len(data)
        hits += len(grep(data, query))
    dt = (time.perf_counter() - t0) * 1000
    return {"bytes": bytes_total, "ms": dt, "hits": hits, "cats": len(cats_to_load)}

print(f"Baseline A size: {len(A_DATA)} bytes\n")
print(f"{'Query':<10} | {'A bytes':>9} {'A ms':>6} {'A hit':>5} | "
      f"{'D bytes':>9} {'D ms':>6} {'D hit':>5} {'cats':>5}")
print("-" * 80)
sa = sd = sah = sdh = 0
for q in QUERIES:
    a = bench_a(q); d = bench_d(q)
    sa += a["bytes"]; sd += d["bytes"]; sah += a["hits"]; sdh += d["hits"]
    print(f"{q:<10} | {a['bytes']:>9} {a['ms']:>6.2f} {a['hits']:>5} | "
          f"{d['bytes']:>9} {d['ms']:>6.2f} {d['hits']:>5} {d['cats']:>5}")
print("-" * 80)
print(f"{'TOTAL':<10} | {sa:>9} {'':>6} {sah:>5} | {sd:>9} {'':>6} {sdh:>5}")
print(f"\nBytes saved: {sa - sd} ({(sa-sd)/sa*100:.1f}%)")
print(f"Hit recovery: D/A = {sdh}/{sah} = {sdh/sah*100:.1f}%")
