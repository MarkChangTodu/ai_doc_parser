# Quick Start

把一份 SoC datasheet PDF 變成 Copilot 可以高效查詢的切片 docs/，**整條流程一行指令**。

---

## 0. 先決條件

| 項目 | 安裝 |
|---|---|
| Python | 3.10+ |
| poppler-utils（提供 `pdftotext`，pdf→md fallback 用） | `sudo apt install poppler-utils` |
| Python deps | `pip install pdfplumber 'pdfminer.six>=20251230' magika tqdm` |
| VS Code Copilot | 一般可用即可，不需特殊設定 |

> WSL / 低記憶體環境：vendor 過的 markitdown 已疊上 `SpooledTemporaryFile` patch + 上游 #1612，41 MB datasheet 在 WSL 上 peak ~600 MB、不會 freeze。

---

## 1. 取得本工具

```bash
cd <你的 zephyr / 任意專案>
git clone https://github.com/MarkChangTodu/ai_doc_parser.git tools/ai_doc_parser
```

`tools/ai_doc_parser/` 完全獨立，不污染 host project；產出寫到 host project 的 `docs/` 與 `.github/`。

---

## 2. 一行跑完整 pipeline

把 PDF 放到專案根目錄，然後：

```bash
./tools/ai_doc_parser/pipeline.sh IMX8MPRM.pdf
```

它會依序做：

| 步驟 | 動作 | 產出 |
|---|---|---|
| 1/3 | `convert/pdf_to_md.py` 用 vendored markitdown 轉 PDF | `docs/source/IMX8MPRM.md`（mtime cache，第二次會 skip） |
| 1/3 | `parse_datasheet.py` 切 sections / 拆 21 個主題 / 抽 register blocks / 寫 section_index.json | `docs/topics/`, `docs/subsystems/`, `docs/registers/`, `docs/section_index.json` |
| 1/3 | 寫 fallback marker + Copilot 規則 | `docs/.source`, `.github/copilot-instructions.md` |
| 2/3 | 顯示 fallback source 路徑 | — |
| 3/3 | 跑 bench 對照（DB vs 單檔 MD） | stdout 表格 |

跑完 reload VS Code window（`Ctrl+Shift+P` → **Reload Window**）讓 Copilot 吃到新規則。

---

## 3. 用 Copilot 查資料

直接在 Copilot Chat 問，它會先讀 `docs/topics/main.md` → 跳到對應 sub-file，例如：

```
規劃 i.MX8MP 上 HDMI driver bring-up 流程
列出 ECSPI3 的 register 與 reset value
USB OTG controller 的 clock gate 是哪一個？
```

回答會帶 `docs/...:L<n>-L<m>` 引用，可以直接跳到原文位置。

---

## 4. Fallback 查詢（找不到答案時）

切過的 docs/ 可能漏掉一些散落內容。Copilot 在規則裡被指示先看 sub-files，找不到再退回完整 .md：

```bash
# 關鍵字
python3 tools/ai_doc_parser/fallback/lookup.py grep "I2C clock"

# 看某行附近原文
python3 tools/ai_doc_parser/fallback/lookup.py window 294176 --before 5 --after 8

# 來源檔案資訊
python3 tools/ai_doc_parser/fallback/lookup.py info
```

> 預設讀 `docs/.source`；可用 `--md path/to.md` 或 `AI_DOC_SOURCE_MD` 覆蓋。

---

## 5. 常用旗標

```bash
# 跳過 bench（CI / 純更新 docs）
AI_DOC_NO_BENCH=1 ./tools/ai_doc_parser/pipeline.sh IMX8MPRM.pdf

# 用已有的 .md，跳過 PDF 轉檔
./tools/ai_doc_parser/pipeline.sh IMX8MPRM.md

# 只跑 parse，不跑 pipeline 包裝
python3 tools/ai_doc_parser/parse_datasheet.py IMX8MPRM.pdf

# 增量迭代：只重切某個 section / 行範圍 / 先 dry-run 看寫什麼
python3 tools/ai_doc_parser/parse_datasheet.py IMX8MPRM.md --section 13.11 --dry-run
python3 tools/ai_doc_parser/parse_datasheet.py IMX8MPRM.md --section 13.11 --write
python3 tools/ai_doc_parser/parse_datasheet.py IMX8MPRM.md --range 239795 241153 --write

# 只跑 bench（對既有 docs/）
python3 tools/ai_doc_parser/bench/bench_md_vs_db.py \
  --workspace . --docs docs --md docs/source/IMX8MPRM.md
```

---

## 6. 預期效益（IMX8MPRM, 41 MB / ~1500 頁實測）

| | 切過的 docs/ DB | 單檔 MD baseline | 改善 |
|---|---:|---:|---|
| 每次 query 載入 | ~100 KB | 15 MB | **~99% 少** |
| 15 query 總時間 | 43 ms | 1.4 s | **~33× 快** |
| Cold PDF→docs | 12 min, 600 MB peak | — | 不會 OOM WSL |
| Warm（cache 命中） | 4 s | — | — |

---

## 7. 出問題？

| 症狀 | 排查 |
|---|---|
| `pdftotext: command not found` | `sudo apt install poppler-utils` |
| `ModuleNotFoundError: pdfplumber` | `pip install pdfplumber pdfminer.six magika` |
| Copilot 沒讀到規則 | Reload Window；確認 `.github/copilot-instructions.md` 存在 |
| Bench 某 query 顯示 `subs=0` | `bench_md_vs_db.py` 的 `CATEGORIES` 已動態 import 自 parser，若仍 0 hits 表示 query 字串真的不在任何 category 群組 |
| 大 PDF WSL freeze | 確認 `vendor/markitdown/__about__.py` >= `0.1.6b2` 且 `_pdf_converter.py` 同時有 `page.close()` 與 `SpooledTemporaryFile` |

詳細設計與 patch 來龍去脈見 [README.md](README.md) 與 [vendor/_pdf_converter.patch](vendor/_pdf_converter.patch)。
