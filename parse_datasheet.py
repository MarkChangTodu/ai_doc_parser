import os
import re
import sys
import shutil
import subprocess

# Make convert/ importable so we can reuse pdf_to_md.convert_pdf().
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Workspace root is two levels above this script:
#   <workspace>/tools/ai_doc_parser/parse_datasheet.py
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WORKSPACE_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))

# Default input (used when no CLI arg is given)
DEFAULT_INPUT = os.path.join(WORKSPACE_DIR, "IMX8MPRM.txt")
INPUT_FILE = DEFAULT_INPUT
BASE_DIR = os.path.join(WORKSPACE_DIR, "docs")

SUB_DIR = os.path.join(BASE_DIR, "subsystems")
REG_DIR = os.path.join(BASE_DIR, "registers")
MISC_DIR = os.path.join(BASE_DIR, "misc")
SRC_DIR = os.path.join(BASE_DIR, "source")
SOURCE_MARKER = os.path.join(BASE_DIR, ".source")
COPILOT_INSTRUCTIONS_PATH = os.path.join(WORKSPACE_DIR, ".github", "copilot-instructions.md")

ALIAS = {
    "graphics processing unit": "gpu",
    "video processing unit": "vpu",
}

# ---------- Topic categories (Layout D) ----------
# A section may belong to MULTIPLE categories (multi-tag).
# Keywords are matched (case-insensitive substring) against the section title.
CATEGORIES = {
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
    "mipi":    ["mipi"],  # cross-cutting tag
    "hdmi":    ["hdmi"],  # cross-cutting tag
}

# ---------- 工具 ----------
def normalize(name):
    return re.sub(r'[^a-z0-9]+', '_', name.lower()).strip("_")

def get_level(section):
    return section.count(".")

def classify(section, title):
    if get_level(section) <= 1:
        return "subsystems"
    if "REGISTER" in title.upper():
        return "registers"
    return "misc"

def extract_keywords(title, body):
    words = re.findall(r'\b[A-Za-z]{4,}\b', title + " " + body[:800])
    freq = {}
    for w in words:
        w = w.lower()
        freq[w] = freq.get(w, 0) + 1

    sorted_words = sorted(freq.items(), key=lambda x: -x[1])
    return [w for w, _ in sorted_words[:8]]

def is_register_block(text):
    t = text.lower()
    return (
        "register" in t and
        ("bit" in t or "field" in t or "offset" in t)
    )

# ---------- PDF → TXT 轉換 ----------
def pdf_to_txt(pdf_path):
    """Convert a PDF to a plain-text file alongside it. Cached by mtime."""
    stem, _ = os.path.splitext(pdf_path)
    txt_path = stem + ".txt"

    if os.path.exists(txt_path) and \
       os.path.getmtime(txt_path) >= os.path.getmtime(pdf_path):
        print(f"✅ Using cached TXT: {txt_path}")
        return txt_path

    # Try poppler's pdftotext (best layout preservation)
    try:
        print(f"→ Converting via pdftotext: {pdf_path}")
        subprocess.run(
            ["pdftotext", "-layout", pdf_path, txt_path],
            check=True,
        )
        print(f"✅ Wrote {txt_path}")
        return txt_path
    except FileNotFoundError:
        print("⚠️  pdftotext not found, trying pypdf fallback...")
    except subprocess.CalledProcessError as e:
        print(f"⚠️  pdftotext failed ({e}), trying pypdf fallback...")

    # Fallback: pypdf (pure-python)
    try:
        from pypdf import PdfReader
    except ImportError:
        try:
            from PyPDF2 import PdfReader  # type: ignore
        except ImportError:
            raise SystemExit(
                "❌ No PDF backend available. Install one of:\n"
                "   sudo apt install poppler-utils    # provides pdftotext\n"
                "   pip install pypdf                 # python fallback"
            )

    print(f"→ Converting via pypdf: {pdf_path}")
    reader = PdfReader(pdf_path)
    with open(txt_path, "w", encoding="utf-8") as f:
        for i, page in enumerate(reader.pages):
            f.write(page.extract_text() or "")
            f.write("\n")
            if (i + 1) % 50 == 0:
                print(f"   ... {i+1}/{len(reader.pages)} pages")
    print(f"✅ Wrote {txt_path}")
    return txt_path

def resolve_input(arg):
    """Accept a .pdf, .md or .txt path; return a text path ready to parse.

    For .pdf: converts via the vendored markitdown and stores the result in
    ``docs/source/<stem>.md`` (single source of truth, mtime-cached).
    For .md : copies into ``docs/source/<stem>.md`` so all data lives in one
    place; subsequent runs are mtime-cached.
    For .txt: kept for backwards compatibility (uses pdftotext output).
    """
    if not os.path.exists(arg):
        raise SystemExit(f"❌ Input not found: {arg}")
    ext = os.path.splitext(arg)[1].lower()
    if ext == ".pdf":
        return pdf_to_md(arg)
    if ext == ".md":
        return adopt_md(arg)
    if ext == ".txt":
        return arg
    raise SystemExit(f"❌ Unsupported file type: {arg} (expect .pdf, .md or .txt)")


def pdf_to_md(pdf_path):
    """Convert PDF -> Markdown via vendored markitdown, output under docs/source/."""
    from convert.pdf_to_md import convert_pdf  # local import: avoids needing markitdown deps for txt-only flow

    os.makedirs(SRC_DIR, exist_ok=True)
    stem = os.path.splitext(os.path.basename(pdf_path))[0]
    out = os.path.join(SRC_DIR, stem + ".md")
    md_path = convert_pdf(pdf_path, out_path=out)
    print(f"✅ Markdown ready: {md_path}")
    return str(md_path)


def adopt_md(md_path):
    """Copy a pre-existing .md into docs/source/ (mtime-cached) and return its path."""
    os.makedirs(SRC_DIR, exist_ok=True)
    src = os.path.abspath(md_path)
    dst = os.path.join(SRC_DIR, os.path.basename(src))
    if os.path.abspath(src) == os.path.abspath(dst):
        return dst  # already in place
    if os.path.exists(dst) and os.path.getmtime(dst) >= os.path.getmtime(src):
        print(f"✅ Using cached MD: {dst}")
        return dst
    shutil.copy2(src, dst)
    print(f"✅ Copied {src} -> {dst}")
    return dst

# ---------- 主解析 ----------
def parse_and_extract():
    print("✅ Parser started")

    if not os.path.exists(INPUT_FILE):
        print("❌ INPUT_FILE not found")
        return

    with open(INPUT_FILE, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()

    print(f"✅ Total lines: {len(lines)}")

    sections = []
    i = 0

    # ✅ section parsing
    while i < len(lines):
        line = lines[i].strip()

        match = re.match(r'^\s*Chapter\s+(\d+)\s+(.+)', line, re.IGNORECASE)
        if match:
            sections.append((match.group(1), match.group(2).strip(), i))
            i += 1
            continue

        match = re.match(r'^\s*(\d+(\.\d+)?)$', line)
        if match and i + 1 < len(lines):
            next_line = lines[i + 1].strip()
            if len(next_line) > 5:
                sections.append((match.group(1), next_line, i))
                i += 2
                continue

        match = re.match(r'^\s*(\d+(\.\d+)?)\s+(.+)', line)
        if match:
            sections.append((match.group(1), match.group(3).strip(), i))
            i += 1
            continue

        i += 1

    print(f"✅ Found {len(sections)} sections")

    for d in [SUB_DIR, REG_DIR, MISC_DIR]:
        os.makedirs(d, exist_ok=True)

    reg_count = 0

    # ---------- 寫 subsystem + register ----------
    for idx in range(len(sections)):
        section, title, start = sections[idx]
        end = sections[idx+1][2] if idx+1 < len(sections) else len(lines)

        body = "".join(lines[start:end]).strip()

        if len(body) < 500:
            continue

        category = classify(section, title)

        filename = normalize(title)
        for k, v in ALIAS.items():
            if k in title.lower():
                filename = v

        filename = filename[:60] + ".md"

        # subsystem
        if category == "subsystems":
            path = os.path.join(SUB_DIR, filename)

            with open(path, "w", encoding="utf-8") as f:
                f.write(f"# {title}\n\n")
                f.write(f"Section: {section}\n\n")

                keywords = extract_keywords(title, body)
                if keywords:
                    f.write("## Keywords\n")
                    f.write(", ".join(keywords) + "\n\n")

                f.write("## Raw Specification\n\n")
                f.write(body)

        # register extract
        blocks = body.split("\n\n")

        for i_b, block in enumerate(blocks):
            if is_register_block(block):
                reg_file = filename.replace(".md", f"_reg_{i_b}.md")
                reg_path = os.path.join(REG_DIR, reg_file)

                with open(reg_path, "w", encoding="utf-8") as out:
                    out.write(block)

                reg_count += 1

    create_index(sections)
    create_topic_index(sections)
    create_driver_prompt()
    write_source_marker()
    create_copilot_instructions()
    create_search_rules_doc()

    print(f"✅ Extracted {reg_count} register blocks")
    print("✅ ✅ ✅ ALL DONE")

# ---------- subsystem index (chapter-level, short fallback) ----------
def create_index(sections):
    index_path = os.path.join(BASE_DIR, "subsystems_index.md")

    with open(index_path, "w") as f:
        f.write("# Subsystems Index (chapter-level)\n\n")
        f.write("For topic-based lookup, prefer `docs/topics/main.md`.\n\n")

        for section, title, _ in sections:
            if get_level(section) == 0:  # only Chapter-level entries
                name = normalize(title)
                for k, v in ALIAS.items():
                    if k in title.lower():
                        name = v
                f.write(f"- {title} ({section}) -> {name}.md\n")

# ---------- Topic-based index (Layout D, multi-category) ----------
def categorize_multi(title):
    """Return list of categories matching the title (may be empty)."""
    t = " " + title.lower() + " "
    cats = []
    for cat, kws in CATEGORIES.items():
        for kw in kws:
            if kw in t:
                cats.append(cat)
                break
    return cats

def create_topic_index(sections):
    topic_dir = os.path.join(BASE_DIR, "topics")
    os.makedirs(topic_dir, exist_ok=True)

    by_cat = {cat: [] for cat in CATEGORIES}
    by_cat["misc"] = []

    for sec, title, _ in sections:
        if get_level(sec) > 1:
            continue
        cats = categorize_multi(title)
        if not cats:
            by_cat["misc"].append((sec, title))
        else:
            for c in cats:
                by_cat[c].append((sec, title))

    # main.md - topic dispatcher
    main_path = os.path.join(topic_dir, "main.md")
    with open(main_path, "w") as f:
        f.write("# Topic Index (main dispatcher)\n\n")
        f.write("Use this file FIRST. Match query keyword against the keyword list of each topic, then open `topics/<topic>.md`.\n\n")
        for cat in sorted(by_cat.keys()):
            kws = CATEGORIES.get(cat, [cat])
            count = len(by_cat[cat])
            f.write(f"- **{cat}** ({count} entries) keywords: {', '.join(kws)} -> topics/{cat}.md\n")

    # per-category file
    for cat, entries in by_cat.items():
        path = os.path.join(topic_dir, f"{cat}.md")
        with open(path, "w") as f:
            f.write(f"# Topic: {cat}\n\n")
            f.write(f"{len(entries)} entries.\n\n")
            for sec, title in entries:
                fname = normalize(title)
                for k, v in ALIAS.items():
                    if k in title.lower():
                        fname = v
                fname = fname[:60] + ".md"
                f.write(f"- {title} ({sec}) -> subsystems/{fname}\n")

    print(f"✅ topic index built: {len(by_cat)} topics, total entries (with multi-tag): {sum(len(v) for v in by_cat.values())}")

# ---------- ✅ driver_prompt 自動建立 ----------
def create_driver_prompt():
    prompt_path = os.path.join(BASE_DIR, "driver_prompt.md")

    with open(prompt_path, "w") as f:
        f.write("""# Driver Query Template

You are an embedded systems engineer working on SoC firmware.

Rules:
- Use ONLY information from workspace files (docs/)
- Do NOT guess
- If something is not in the spec, say: "not in spec"

---

## Task

1. Identify subsystem
2. Find related registers
3. Provide step-by-step initialization flow

---

## Output Format

### Subsystem
(Name)

### Key Registers
(List)

### Initialization Steps
1. Step 1
2. Step 2

### Notes
""")

    print("✅ driver_prompt.md created")

# ---------- source marker (for fallback/lookup.py) ----------
def write_source_marker():
    """Record the absolute path of the source .md so fallback/lookup.py can find it.

    Only written when the input is a markdown file in docs/source/. For .txt
    inputs the marker is skipped (lookup helper falls back to other resolution).
    """
    if not INPUT_FILE.lower().endswith(".md"):
        return
    os.makedirs(BASE_DIR, exist_ok=True)
    with open(SOURCE_MARKER, "w", encoding="utf-8") as f:
        f.write(os.path.abspath(INPUT_FILE) + "\n")
    print(f"✅ source marker: {SOURCE_MARKER}")


# ---------- ✅ copilot-instructions 自動建立 ----------
def create_copilot_instructions():
    os.makedirs(os.path.dirname(COPILOT_INSTRUCTIONS_PATH), exist_ok=True)

    src_rel = os.path.relpath(INPUT_FILE, WORKSPACE_DIR) if INPUT_FILE else "docs/source/<datasheet>.md"
    has_md_source = INPUT_FILE.lower().endswith(".md")

    fallback_section = ""
    if has_md_source:
        fallback_section = f"""
## Fallback (when `docs/` does NOT contain the answer)

The original Markdown source is preserved at `{src_rel}`. **NEVER read it as a
whole** (it can be tens of MB). Instead, use the helper script that does
targeted line-number lookups:

```bash
# 1. Find candidate line numbers for a keyword (default: <=50 results, case-insensitive)
python3 tools/ai_doc_parser/fallback/lookup.py grep "<keyword>"

# 2. Read a window of lines around a chosen line
python3 tools/ai_doc_parser/fallback/lookup.py window <line> --before 20 --after 100

# 3. (Optional) inspect file size / line count
python3 tools/ai_doc_parser/fallback/lookup.py info
```

Fallback rules:
- Use fallback **only** when `docs/topics/`, `docs/subsystems/`, `docs/registers/`
  and `docs/misc/` together cannot answer.
- After looking up a window, cite the source as `{src_rel}:L<start>-L<end>`.
- Still respect: do NOT guess, do NOT use general i.MX8MP knowledge.
"""

    content = f"""# Copilot Instructions for IMX8MP Driver Development

These instructions apply to all driver/firmware tasks in this workspace.
They were generated by `tools/ai_doc_parser/parse_datasheet.py`.

## Source of Truth (in priority order)
1. `docs/topics/main.md`            -- topic dispatcher (open FIRST)
2. `docs/topics/<topic>.md`         -- per-topic candidate lists
3. `docs/subsystems/*.md`           -- per-subsystem specifications
4. `docs/registers/*.md`            -- register field tables
5. `docs/misc/*.md`                 -- everything else that survived parsing
6. `docs/subsystems_index.md`       -- chapter-level fallback index
7. `{src_rel}` via `fallback/lookup.py` -- catch-all for what `docs/` missed

## Hard Rules
- Do NOT guess.
- Do NOT use external / general knowledge of i.MX8MP that is not present in
  the workspace files listed above.
- Do NOT read the raw source `.md` (or any `.txt`) wholesale; use the
  fallback helper for targeted lookups (see section below).
- If a fact is not in any of the listed sources, answer **exactly**:
  `not in spec`.
- Always cite the source file (e.g. `docs/subsystems/hdmi.md` or
  `{src_rel}:L1234-L1334`) when stating a fact.

## Default Workflow for Driver Tasks
1. Open `docs/topics/main.md`; match the query keyword(s) against the topic
   keyword lists. A query may map to MULTIPLE topics (e.g. "MIPI" -> display
   + camera + mipi).
2. Open every matching `docs/topics/<topic>.md` to enumerate candidate
   subsystem files.
3. Open the matching `docs/subsystems/*.md` file(s).
4. Pull related register details from `docs/registers/*.md`.
5. If steps 1-4 leave gaps, use **Fallback** (below).
6. Produce a step-by-step initialization flow in the required output format.
{fallback_section}
## Figures (text-only spec, no image extraction)

The spec preserves figure **captions** as text (e.g. `Figure 12-1. GPT Block
Diagram`) but the figures themselves are NOT available to you. ~28% of
figures (block diagrams, timing diagrams, state machines, key flow charts)
carry information that is not fully expressible in surrounding prose.

When you encounter a figure reference and the surrounding text alone is
insufficient to answer:

- Do NOT guess what the figure shows.
- Do NOT invent block names, signal connections, timing values, or state
  transitions that are not explicitly written in nearby paragraphs or
  tables.
- Output a single line in this exact format:

  ```
  ⚠️ Need image: <Figure N-M. caption text>  (<file>:L<line>)
  ```

  Then continue answering the parts of the question that the text **does**
  cover. Mark figure-dependent facts as `not in spec` per the Hard Rules.

This lets the human reader open the original PDF only for the specific
figures that actually block progress, instead of pre-extracting all 600+
figures speculatively.

## Required Output Format

### Subsystem
(Name)

### Key Registers
(List with offset + bit fields. Cite source file for each row.)

### Initialization Steps
1. Step 1 (cite source)
2. Step 2 (cite source)

### Notes
- Mark anything not in spec as `not in spec`.
"""

    with open(COPILOT_INSTRUCTIONS_PATH, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"✅ {COPILOT_INSTRUCTIONS_PATH} created")

# ---------- ✅ SEARCH_RULES.md (human-readable mirror of the rules) ----------
def create_search_rules_doc():
    """Write a human-readable description of the active search rules.

    Lives at tools/ai_doc_parser/SEARCH_RULES.md so it is version-controlled
    alongside the parser. Regenerated on every pipeline run, so any change
    to CATEGORIES or the rule template propagates automatically.
    """
    from datetime import datetime, timezone

    out_path = os.path.join(SCRIPT_DIR, "SEARCH_RULES.md")
    src_rel = os.path.relpath(INPUT_FILE, WORKSPACE_DIR) if INPUT_FILE else "docs/source/<datasheet>.md"
    has_md_source = INPUT_FILE.lower().endswith(".md")
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Render CATEGORIES table
    cat_rows = []
    for name, kws in CATEGORIES.items():
        kw_str = ", ".join(f"`{k.strip()}`" for k in kws)
        cat_rows.append(f"| `{name}` | {kw_str} |")
    cat_table = "\n".join(cat_rows)

    fallback_block = f"""## 4. Fallback (when `docs/` cannot answer)

The original full Markdown is preserved at `{src_rel}` (tens of MB). Copilot is
**forbidden from reading it whole**; it must use the line-targeted helper:

```bash
# (a) find candidate line numbers (<=50 results, case-insensitive)
python3 tools/ai_doc_parser/fallback/lookup.py grep "<keyword>"

# (b) read a window around a chosen line
python3 tools/ai_doc_parser/fallback/lookup.py window <line> --before 20 --after 100

# (c) inspect file size / line count
python3 tools/ai_doc_parser/fallback/lookup.py info
```

Citation format for fallback hits: `{src_rel}:L<start>-L<end>`.
""" if has_md_source else """## 4. Fallback

_No `.md` source registered for this run; `fallback/lookup.py` is unavailable._
"""

    content = f"""# Search Rules (active)

_Auto-generated by `tools/ai_doc_parser/parse_datasheet.py` on {ts}._
_Do not hand-edit; rerun `pipeline.sh` to refresh._

This document mirrors what Copilot is told via
[`.github/copilot-instructions.md`](../../.github/copilot-instructions.md).
Every pipeline run regenerates **both** files from the same source so they
stay in sync.

Source of truth for this run: `{src_rel}`

---

## 1. Source priority (high → low)

Copilot must walk this list top-down. Lower tiers are only consulted when
higher tiers cannot answer.

| # | Source | Purpose |
|---|---|---|
| 1 | `docs/topics/main.md` | Topic dispatcher — always opened FIRST |
| 2 | `docs/topics/<topic>.md` | Per-topic candidate sub-file lists |
| 3 | `docs/subsystems/*.md` | Per-subsystem specifications |
| 4 | `docs/registers/*.md` | Register field tables (offset / bits) |
| 5 | `docs/misc/*.md` | Sections that did not match any topic |
| 6 | `docs/subsystems_index.md` | Chapter-level fallback index |
| 7 | `{src_rel}` via `fallback/lookup.py` | Catch-all for what `docs/` missed |

---

## 2. Hard rules

| Forbidden | Required |
|---|---|
| Guessing | Answer `not in spec` if absent |
| Using external / general i.MX8MP knowledge | Use only the 7 sources above |
| Wholesale reading `docs/source/*.md` or any `.txt` | Use `fallback/lookup.py` for line-window lookups |
| Stating facts without provenance | Cite `<file>` or `<file>:L<start>-L<end>` |

---

## 3. Default workflow

```
Query in
  │
  ▼
[1] Open docs/topics/main.md, match keyword(s) against topic keyword lists.
    A query may match MULTIPLE topics (e.g. "MIPI" → display + camera + mipi).
  │
  ▼
[2] Open every matching docs/topics/<topic>.md, list candidate sub-files.
  │
  ▼
[3] Open the matching docs/subsystems/*.md.
  │
  ▼
[4] Pull register details from docs/registers/*.md.
  │
  ▼
[5] Gaps remaining? → fallback/lookup.py grep + window
  │
  ▼
[6] Answer in the Required Output Format with source citations on every line.
```

---

{fallback_block}
---

## 4b. Figures (text-only spec, no image extraction)

The spec preserves figure **captions** as text (e.g. `Figure 12-1. GPT Block
Diagram`) but the figures themselves are NOT extracted. About **28% of
figures** in this datasheet carry information not fully reconstructable
from surrounding prose:

| Caption type | Approx. count | Image content recoverable from text? |
|---|---:|---|
| Block diagram | ~87 | No — wiring/labels not enumerated in prose |
| Timing diagram | ~59 | Partial — numeric values usually in EC tables |
| State machine | ~19 | No |
| Flow chart | ~46 | Partial — step lists usually inline |
| Register/bit layout | ~42 | Yes — already extracted as text tables |
| Pinout / ball map | 0 | Use NXP pinmux tool / xlsx, not the PDF |

When Copilot hits a figure-dependent question, the rule is:

```
⚠️ Need image: <Figure N-M. caption text>  (<file>:L<line>)
```

Then answer the textual parts of the question and mark the rest
`not in spec`. The human reader opens the original PDF only for the
specific figures that actually block progress — no upfront figure
extraction needed.

---

## 5. Topic categories ({len(CATEGORIES)} active)

A section is multi-tagged into every topic whose keyword list matches its
title (case-insensitive substring). To change the routing, edit the
`CATEGORIES` dict in `parse_datasheet.py` — this table will refresh on the
next pipeline run, and `bench_md_vs_db.py` reads the same dict dynamically
so the bench cannot drift.

| Topic | Keywords |
|---|---|
{cat_table}

---

## 6. Required output format (Copilot answers)

```markdown
### Subsystem
(Name)

### Key Registers
(offset + bit fields, one citation per row)

### Initialization Steps
1. Step 1 (cite source)
2. Step 2 (cite source)

### Notes
- Anything missing from spec marked `not in spec`
```

---

## 7. Why this design

| Choice | Problem it solves |
|---|---|
| 7-tier priority + `main.md` first | Avoid loading the whole 15 MB markdown into a single prompt |
| {len(CATEGORIES)} topics, with `comm` split into `comm_i2c/serial/can/net/pcie/usb` | Average query loads ~100 KB instead of 15 MB — measured **99% bytes saved, ~33× faster** |
| Forbid external knowledge + force `not in spec` | Hard grounding, no hallucinated registers |
| Mandatory citations | Every claim is one click away from the source line |
| Fallback is line-window only | Recover missed content without dumping the whole datasheet into the prompt |
| Fallback is last resort | Most queries take the fast path; precision over recall |

---

## 8. Verifying the rules are loaded in VS Code

1. After `pipeline.sh` finishes, **Reload Window** (`Ctrl+Shift+P` → *Developer: Reload Window*).
2. Open a fresh Copilot Chat (the trash-can / *New Chat* button).
3. Ask: *"List your priority order for IMX8MP driver questions."*
4. The reply must mirror section 1 above. If it does not, check:
   - `.github/copilot-instructions.md` exists at workspace root
   - VS Code is opened on the workspace root (not a sub-folder)
   - Setting `github.copilot.chat.codeGeneration.useInstructionFiles` is `true` (default)
"""

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"✅ {out_path} created")

# ---------- main ----------
if __name__ == "__main__":
    if len(sys.argv) > 1:
        INPUT_FILE = resolve_input(sys.argv[1])
        print(f"✅ Input resolved to: {INPUT_FILE}")
    parse_and_extract()
