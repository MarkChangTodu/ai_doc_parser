import os
import re
import sys
import subprocess

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
    """Accept a .pdf or .txt path; return a .txt path ready to parse."""
    if not os.path.exists(arg):
        raise SystemExit(f"❌ Input not found: {arg}")
    ext = os.path.splitext(arg)[1].lower()
    if ext == ".pdf":
        return pdf_to_txt(arg)
    if ext == ".txt":
        return arg
    raise SystemExit(f"❌ Unsupported file type: {arg} (expect .pdf or .txt)")

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
    create_copilot_instructions()

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

# ---------- ✅ copilot-instructions 自動建立 ----------
def create_copilot_instructions():
    os.makedirs(os.path.dirname(COPILOT_INSTRUCTIONS_PATH), exist_ok=True)

    with open(COPILOT_INSTRUCTIONS_PATH, "w", encoding="utf-8") as f:
        f.write("""# Copilot Instructions for IMX8MP Driver Development

These instructions apply to all driver/firmware tasks in this workspace.

## Source of Truth
- Use ONLY information from the `docs/` folder (parsed from IMX8MPRM.txt).
- **Topic dispatcher (use FIRST):** `docs/topics/main.md`
- Per-topic indexes: `docs/topics/<topic>.md`
- Chapter-level fallback index: `docs/subsystems_index.md`
- Subsystem specs: `docs/subsystems/*.md`
- Register details: `docs/registers/*.md`
- Misc specs: `docs/misc/*.md`

## Rules
- Do NOT guess.
- Do NOT use external/general knowledge of i.MX8MP that is not present in `docs/`.
- Do NOT read `IMX8MPRM.txt` directly; always use the parsed files under `docs/`.
- If something is not in the spec, say exactly: "not in spec".
- Always cite the source file (e.g. `docs/subsystems/hdmi.md`) when stating a fact.

## Default Workflow for Driver Tasks
1. Open `docs/topics/main.md` and match the query against topic keyword lists.
   A query may match MULTIPLE topics (e.g. "MIPI" -> display + camera + mipi).
2. Open all matching `docs/topics/<topic>.md` to find candidate subsystem files.
3. Read the matching `docs/subsystems/*.md` file(s).
4. Pull related registers from `docs/registers/*.md`.
5. Provide a step-by-step initialization flow.

## Required Output Format

### Subsystem
(Name)

### Key Registers
(List with offset + bit fields, cite source file)

### Initialization Steps
1. Step 1 (cite source)
2. Step 2 (cite source)

### Notes
- Mark anything not in spec.
""")

    print(f"✅ {COPILOT_INSTRUCTIONS_PATH} created")

# ---------- main ----------
if __name__ == "__main__":
    if len(sys.argv) > 1:
        INPUT_FILE = resolve_input(sys.argv[1])
        print(f"✅ Input resolved to: {INPUT_FILE}")
    parse_and_extract()
