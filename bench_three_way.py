"""Three-way comparison:
  baseline_db : pre-existing  ~/zephyrproject/docs/  (old CATEGORIES with fat 'comm')
  txt_v2_db   : re-parsed     ~/zephyrproject/docs_txt_v2/  (new split CATEGORIES)
  md_db       : MD re-parsed  ~/zephyrproject/docs_md/      (new split CATEGORIES)

Single MD file is also kept as a reference upper bound.

Usage:
  python3 bench_three_way.py
"""
import os
import re
import sys
import time

HOME = os.path.expanduser("~")
MD_FILE = os.path.join(HOME, "zephyrproject", "IMX8MPRM.md")

QUERIES = ["HDMI", "GPU", "LCDIF", "I2C", "MIPI", "DMA", "CSI",
           "ECSPI", "VPU", "USB", "SAI", "CAAM", "USDHC", "ENET", "GPT"]

# Old categories (matches the docs/ that was generated yesterday)
CATEGORIES_OLD = {
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

# New categories (after splitting comm)
CATEGORIES_NEW = {
    "display": ["lcdif", "hdmi", "mipi dsi", "mipi_dsi", "dsi", "dpu", "pxp", "dcss", "display", "lvds"],
    "camera":  ["csi", "mipi csi", "mipi_csi", "isp", "isi", "camera"],
    "audio":   ["sai", "asrc", "pdm", "audmix", "spdif", "mqs", "audio", "i2s"],
    "security":["caam", "snvs", "ocotp", "hab", "sjc", "trustzone", "security", "rdc", "csu"],
    "storage": ["usdhc", "qspi", "flexspi", "nand", "emmc", "sdmmc", " sd "],
    "comm_i2c":    ["i2c"],
    "comm_serial": ["ecspi", "uart", "spi"],
    "comm_can":    ["can", "flexcan"],
    "comm_net":    ["enet", "eqos", "ethernet", "phy"],
    "comm_pcie":   ["pcie"],
    "comm_usb":    ["usb"],
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


def grep_count(buf: bytes, pattern: str) -> int:
    pat = re.compile(re.escape(pattern).encode(), re.IGNORECASE)
    return sum(1 for _ in pat.finditer(buf))


def bench_db(query: str, docs_dir: str, categories: dict) -> dict:
    topics_dir = os.path.join(docs_dir, "topics")
    sub_dir = os.path.join(docs_dir, "subsystems")

    t0 = time.perf_counter()
    main_path = os.path.join(topics_dir, "main.md")
    with open(main_path, "rb") as f:
        main = f.read()
    bytes_total = len(main)

    q = query.lower()
    cats_to_load = set()
    for cat, kws in categories.items():
        for kw in kws:
            kw_clean = kw.strip().lower()
            if kw_clean and (kw_clean in q or q in kw_clean):
                cats_to_load.add(cat)
                break

    if not cats_to_load:
        cats_to_load = {f.replace(".md", "") for f in os.listdir(topics_dir)
                        if f.endswith(".md") and f != "main.md"}

    sub_files: set = set()
    hits_topic = 0
    for cat in cats_to_load:
        path = os.path.join(topics_dir, f"{cat}.md")
        if not os.path.exists(path):
            continue
        with open(path, "rb") as f:
            data = f.read()
        bytes_total += len(data)
        hits_topic += grep_count(data, query)
        for m in re.finditer(rb"->\s*subsystems/([^\s)]+\.md)", data):
            sub_files.add(m.group(1).decode())

    hits_sub = 0
    for fn in sub_files:
        p = os.path.join(sub_dir, fn)
        if not os.path.exists(p):
            continue
        with open(p, "rb") as f:
            d = f.read()
        bytes_total += len(d)
        hits_sub += grep_count(d, query)

    dt = (time.perf_counter() - t0) * 1000
    return {"bytes": bytes_total, "ms": dt,
            "hits": hits_topic + hits_sub,
            "cats": len(cats_to_load), "subs": len(sub_files)}


def bench_md(query: str, data: bytes) -> dict:
    t0 = time.perf_counter()
    hits = grep_count(data, query)
    dt = (time.perf_counter() - t0) * 1000
    return {"bytes": len(data), "ms": dt, "hits": hits}


def run_pass(label: str, docs_dir: str, categories: dict) -> dict:
    if not os.path.isdir(docs_dir):
        print(f"\n[skip] {label}: {docs_dir} not found")
        return None
    print(f"\n=== {label}  ({docs_dir}) ===")
    print(f"{'Query':<8} | {'bytes':>10} {'ms':>7} {'hits':>7} {'cats':>5} {'subs':>5}")
    print("-" * 55)
    sb = sm = sh = 0
    for q in QUERIES:
        r = bench_db(q, docs_dir, categories)
        sb += r["bytes"]; sm += r["ms"]; sh += r["hits"]
        print(f"{q:<8} | {r['bytes']:>10,} {r['ms']:>7.2f} "
              f"{r['hits']:>7} {r['cats']:>5} {r['subs']:>5}")
    print("-" * 55)
    print(f"{'TOTAL':<8} | {sb:>10,} {sm:>7.2f} {sh:>7}")
    return {"bytes": sb, "ms": sm, "hits": sh}


def run_md_pass() -> dict:
    if not os.path.isfile(MD_FILE):
        print(f"\n[skip] MD baseline: {MD_FILE} not found")
        return None
    with open(MD_FILE, "rb") as f:
        data = f.read()
    print(f"\n=== single-file MD  ({MD_FILE}, {len(data)/1024/1024:.1f} MB) ===")
    print(f"{'Query':<8} | {'bytes':>10} {'ms':>7} {'hits':>7}")
    print("-" * 42)
    sb = sm = sh = 0
    for q in QUERIES:
        r = bench_md(q, data)
        sb += r["bytes"]; sm += r["ms"]; sh += r["hits"]
        print(f"{q:<8} | {r['bytes']:>10,} {r['ms']:>7.2f} {r['hits']:>7}")
    print("-" * 42)
    print(f"{'TOTAL':<8} | {sb:>10,} {sm:>7.2f} {sh:>7}")
    return {"bytes": sb, "ms": sm, "hits": sh}


def main():
    base = os.path.join(HOME, "zephyrproject")
    results = {}
    results["baseline_db (txt, old CATEGORIES)"] = run_pass(
        "baseline_db (txt, old CATEGORIES)",
        os.path.join(base, "docs_txt_v1"),
        CATEGORIES_OLD,
    )
    results["txt_v2_db (txt, split comm)"] = run_pass(
        "txt_v2_db (txt, split comm)",
        os.path.join(base, "docs_txt_v2"),
        CATEGORIES_NEW,
    )
    results["md_db (markitdown md, split comm)"] = run_pass(
        "md_db (markitdown md, split comm)",
        os.path.join(base, "docs_md"),
        CATEGORIES_NEW,
    )
    results["single MD file"] = run_md_pass()

    print("\n\n############### SUMMARY ###############")
    print(f"{'Variant':<42} | {'bytes':>12} {'ms':>8} {'hits':>7}")
    print("-" * 78)
    for name, r in results.items():
        if r is None:
            print(f"{name:<42} | {'(skipped)':>12}")
            continue
        print(f"{name:<42} | {r['bytes']:>12,} {r['ms']:>8.2f} {r['hits']:>7}")


if __name__ == "__main__":
    main()
