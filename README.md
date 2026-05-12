# ai_doc_parser — 使用說明

將 SoC 規格書 (PDF / MD / TXT) 自動切割成可被 GitHub Copilot 高效率檢索的結構化 Markdown 知識庫，並產生規則檔讓 Copilot 在本 workspace 中自動遵循「不猜測、只引用 `docs/`」的工作流程。

> **新流程 (推薦)**：`PDF -> markitdown.md -> docs/{topics,subsystems,registers,misc}/*.md`，
> 並保留原始 `.md` 在 `docs/source/` 當 catch-all fallback。
> 使用 vendored markitdown（含 spool + progress 補丁，見 `vendor/_pdf_converter.patch`）。

---

## 1. 功能總覽

| 功能 | 輸出位置 |
|---|---|
| PDF → MD 轉換 (vendored markitdown, 有快取) | `docs/source/<stem>.md` |
| MD 採用（已有 .md 直接餵） | 複製到 `docs/source/<stem>.md` |
| 子系統 spec 切割 | `docs/subsystems/*.md` |
| Register 區塊抽取 | `docs/registers/*.md` |
| 其他段落 | `docs/misc/*.md` |
| Chapter-level 索引 (fallback) | `docs/subsystems_index.md` |
| **Topic dispatcher (主索引)** | `docs/topics/main.md` |
| 主題分類索引 (display / camera / dma / ...) | `docs/topics/<topic>.md` |
| Driver 查詢模板 | `docs/driver_prompt.md` |
| **Copilot 自動規則檔** | `.github/copilot-instructions.md` |
| **Source marker (給 fallback 用)** | `docs/.source` |
| **Catch-all fallback helper** | `fallback/lookup.py` |
| **Markitdown vendored copy** | `vendor/markitdown/` (+ `vendor/_pdf_converter.patch`) |
| **End-to-end pipeline** | `pipeline.sh` |
| **Bench scripts** | `bench/*.py` |

---

## 2. 環境需求

| 項目 | 必要性 | 安裝方式 |
|---|---|---|
| Python 3.10+ | 必要（vendored markitdown 需要） | 系統內建或 `apt install python3` |
| `pdfminer.six >= 20251230` | PDF 必要 | `pip install pdfminer.six` |
| `pdfplumber >= 0.11.9` | PDF 必要 | `pip install pdfplumber` |
| `magika ~= 0.6.1` | PDF 必要 | `pip install magika` |
| `tqdm` | 可選 (進度條) | `pip install tqdm` |
| `pdftotext` (poppler) | 可選 (僅供 .txt 流程) | `sudo apt install poppler-utils` |

> **PDF 處理 backend 順序**：`.pdf` 走 vendored markitdown（spool + progress patch，
> 大檔不爆 RAM）；只在輸入是 `.txt` 時才退回 pdftotext。

---

## 3. 使用方式

### 3.1 一條指令跑完（推薦）

```bash
./tools/ai_doc_parser/pipeline.sh IMX8MPRM.pdf
# 或
./tools/ai_doc_parser/pipeline.sh IMX8MPRM.md
```

流程：
1. `.pdf` → vendored markitdown → `docs/source/IMX8MPRM.md` (mtime cache)
2. 切割 → `docs/{subsystems,registers,misc,topics}/*.md`
3. 寫 `docs/.source`、`.github/copilot-instructions.md`（含 fallback 段）
4. 跑 `bench/bench_md_vs_db.py` 顯示效率對照

> 要跳過 bench：`AI_DOC_NO_BENCH=1 ./pipeline.sh IMX8MPRM.pdf`

### 3.2 直接呼叫 parser

```bash
python3 tools/ai_doc_parser/parse_datasheet.py IMX8MPRM.pdf   # PDF
python3 tools/ai_doc_parser/parse_datasheet.py IMX8MPRM.md    # 已切好的 MD
python3 tools/ai_doc_parser/parse_datasheet.py IMX8MPRM.txt   # 舊流程相容
```

### 3.3 只做 PDF → MD（不切割）

```bash
python3 tools/ai_doc_parser/convert/pdf_to_md.py IMX8MPRM.pdf --out docs/source/IMX8MPRM.md
```

### 3.4 Fallback lookup（給 LLM agent 或人工用）

```bash
# grep 找關鍵字（最多 50 行）
python3 tools/ai_doc_parser/fallback/lookup.py grep "I2C clock"

# 讀某行附近的 ±N 行（預設 -20 / +100）
python3 tools/ai_doc_parser/fallback/lookup.py window 12345

# 看原始 .md 路徑、大小、行數
python3 tools/ai_doc_parser/fallback/lookup.py info
```

來源 .md 的解析順序：`--md` → `AI_DOC_SOURCE_MD` 環境變數 → `docs/.source` → `docs/source/*.md`。

---

## 4. 輸出結構

```
zephyrproject/
├── IMX8MPRM.pdf              # 原始輸入
├── .github/
│   └── copilot-instructions.md   # Copilot 自動載入的規則
└── docs/
    ├── .source                   # 原始 .md 絕對路徑 (fallback/lookup.py 讀)
    ├── driver_prompt.md          # 查詢模板
    ├── subsystems_index.md       # Chapter-level fallback 索引
    ├── source/
    │   └── IMX8MPRM.md           # markitdown 轉出的原文 (catch-all fallback 來源)
    ├── topics/
    │   ├── main.md               # ★ Topic dispatcher (Copilot 先讀這個)
    │   ├── display.md
    │   ├── camera.md
    │   ├── audio.md
    │   ├── dma.md
    │   ├── mipi.md
    │   └── ...
    ├── subsystems/
    │   ├── hdmi.md
    │   ├── lcdif.md
    │   └── ...
    ├── registers/
    │   ├── hdmi_reg_3.md
    │   └── ...
    └── misc/
```

---

## 5. Copilot 整合方式

執行完 parser 後，`.github/copilot-instructions.md` 會被 VS Code Copilot **自動載入**，效果：

| 行為 | 結果 |
|---|---|
| 你輸入「規劃 HDMI driver」 | Copilot 先讀 `docs/topics/main.md` → 找 `hdmi` topic → 讀 `docs/topics/hdmi.md` → 開對應 `subsystems/*.md` |
| Copilot 不會 | 直接讀 `IMX8MPRM.txt`、用網路上的 i.MX8MP 知識回答 |
| 找不到資訊時 | 回 **"not in spec"**，不杜撰 |

> **重要：** 規則套用時機是「**新對話開始時**」。修改規則檔後請開新對話或重新載入 VS Code window 才會生效。

---

## 6. 核心參數可調整

打開 `parse_datasheet.py` 修改以下常數：

```python
# Workspace root 自動從腳本位置推算（../../）
SCRIPT_DIR    = os.path.dirname(os.path.abspath(__file__))
WORKSPACE_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))

DEFAULT_INPUT = os.path.join(WORKSPACE_DIR, "IMX8MPRM.txt")
BASE_DIR      = os.path.join(WORKSPACE_DIR, "docs")

ALIAS = {
    "graphics processing unit": "gpu",   # 把長標題映射成短檔名
    "video processing unit": "vpu",
}

CATEGORIES = {
    "display": ["lcdif", "hdmi", ...],   # 主題分類關鍵字
    ...
}
```

> **路徑是相對的：** `WORKSPACE_DIR` 自動從 `parse_datasheet.py` 的位置往上兩層推得。只要腳本位於 `<workspace>/tools/ai_doc_parser/` 下，整個專案搬到任何路徑都能直接跑。移動腳本位置時記得同步調整 `..` 層數。

要新增主題分類（例如 `network`），加一個項目即可：
```python
"network": ["enet", "eqos", "ethernet", "phy"],
```

---

## 7. 注意事項 ⚠️

### 7.1 覆寫行為
- **每次執行會「完全覆寫」`docs/` 與 `.github/copilot-instructions.md`**
- 如果你手動編輯過這些檔案，**會被蓋掉**
- 想保留手改內容，請先備份或改檔名（例如 `copilot-instructions.local.md`）

### 7.2 PDF 轉換品質取決於 backend
- `pdftotext -layout`：保留欄位排版，最適合 datasheet 表格
- `pypdf`：純 Python，部分表格與欄位會錯位
- **掃描型 PDF（圖片型）兩者都無法處理** — 需先做 OCR（如 `ocrmypdf`）

### 7.3 Section 偵測 regex 是啟發式的
- 目前用 `^\s*\d+(\.\d+)?\s+(.+)` 抓 section 編號
- **副作用：** 表格、清單、頁碼有時會被誤判為 section（PDF 比 TXT 嚴重）
- 若 `subsystems_index.md` 有大量雜訊，調整 `parse_and_extract()` 內的 regex 與長度過濾（`if len(body) < 500: continue`）

### 7.4 Topic 分類是關鍵字啟發式
- `CATEGORIES` 內的關鍵字用 substring 比對（lowercase）
- 一個 section 可能屬於多個 topic（multi-tag），這是設計上的「召回優先」
- 若某個技術詞沒命中 → 進 `misc.md`，可隨時擴充 keyword

### 7.5 快取機制
- TXT 比 PDF 新就跳過轉換
- **手動修改 PDF 後若 mtime 沒更新**，會誤用舊 TXT → 用 `rm IMX8MPRM.txt` 強制重轉
- 路徑非絕對時，TXT 會寫在 PDF 旁邊（同目錄、同 stem 名）

### 7.6 Register 抽取規則
- 條件：段落內同時包含 `register` 與 (`bit` 或 `field` 或 `offset`)
- **誤判可能：** 一般說明若提到 "register bit" 也會被切出
- 真正要用 register 資料時，建議交叉比對 `subsystems/*.md` 內文

### 7.7 不要把 `IMX8MPRM.txt` 提交到 Git
- 1M+ 行，會嚴重拖慢 grep / Copilot 索引
- 建議在 `.gitignore` 加上：
  ```
  IMX8MPRM.txt
  IMX8MPRM.pdf       # 看授權
  ```

### 7.8 大型 PDF 第一次轉換較慢
- IMX8MPRM (~42 MB) 用 `pdftotext` 約數十秒
- `pypdf` 可能要數分鐘
- 之後依快取直接跳過

### 7.9 跨平台
- 只在 Linux/WSL 測試過
- Windows 上若沒有 `pdftotext.exe`，會自動 fallback 到 `pypdf`
- 路徑使用相對推算（以 `parse_datasheet.py` 位置為基準），整個 workspace 搬到任何位置都可直接執行，不需修改常數

---

## 8. 常見問題排除

| 症狀 | 原因 | 解法 |
|---|---|---|
| `pdftotext not found` | poppler 未安裝 | `sudo apt install poppler-utils` 或 `pip install pypdf` |
| `INPUT_FILE not found` | 預設路徑不存在 | 加 CLI 參數：`parse_datasheet.py /full/path/x.pdf` |
| Copilot 沒套用規則 | 對話建立時尚未存在規則檔 | 重新載入 VS Code window 或開新對話 |
| `subsystems_index.md` 空白或極短 | TXT 沒有 `Chapter N` 字樣 | 檢查 PDF 章節格式，或調整 regex |
| Topic 命中很少 | 關鍵字沒覆蓋到該技術 | 擴充 `CATEGORIES` 字典 |
| 想關掉某個產出 | — | 註解 `parse_and_extract()` 結尾的對應 `create_*()` 呼叫 |

---

## 9. 適用文件

理論上適用於任何**有章節編號**的技術 PDF：
- ✅ NXP / TI / ST / Renesas SoC reference manual
- ✅ Linux kernel 文件 (有 chapter heading)
- ⚠️ 學術論文（章節結構通常不同，需調整 regex）
- ❌ 純圖片型 PDF（先 OCR）
- ❌ 無編號散文（無法切割）

---

## 10. 完整工作流程示意

```bash
# 1. 把 PDF 放到 workspace root
cp ~/Downloads/IMX8MPRM.pdf .

# 2. 執行 parser
python3 tools/ai_doc_parser/parse_datasheet.py IMX8MPRM.pdf

# 3. 確認輸出
ls docs/topics/                       # 應看到 main.md 與各 topic
cat .github/copilot-instructions.md   # 確認規則檔

# 4. 重新載入 VS Code window
# Ctrl+Shift+P → "Developer: Reload Window"

# 5. 開新對話
# 直接問 Copilot："規劃 HDMI driver bring-up"
# Copilot 會自動依規則去 docs/topics/main.md 開始查
```
