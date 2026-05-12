# parse_datasheet.py 快速使用

## 三步驟

```bash
# 1. 把 PDF 放到專案根目錄
cp ~/Downloads/IMX8MPRM.pdf .

# 2. 執行
python3 tools/ai_doc_parser/parse_datasheet.py IMX8MPRM.pdf

# 3. 重新載入 VS Code window（Ctrl+Shift+P → Reload Window）
```

完成後直接問 Copilot：「規劃 HDMI driver bring-up」即可。

## 產生什麼

| 路徑 | 用途 |
|---|---|
| `docs/topics/main.md` | Copilot 先讀的主題索引 |
| `docs/subsystems/*.md` | 各子系統 spec |
| `docs/registers/*.md` | Register 細節 |
| `.github/copilot-instructions.md` | 自動套用給 Copilot 的規則 |

## 注意

- 每次執行會**完全覆寫** `docs/` 與規則檔
- 第一次轉 PDF 約 30 秒，之後有快取
- 沒裝 `pdftotext`：`sudo apt install poppler-utils`

詳細請看 [README.md](README.md)。
