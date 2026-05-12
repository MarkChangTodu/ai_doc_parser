#!/usr/bin/env bash
# End-to-end pipeline:
#   PDF (or MD) -> docs/source/<stem>.md  (markitdown)
#                -> docs/{topics,subsystems,registers,misc}/*.md  (parse_datasheet.py)
#                -> .github/copilot-instructions.md (with fallback section)
#                -> docs/.source (so fallback/lookup.py knows the source)
#
# Usage:
#   ./pipeline.sh path/to/datasheet.pdf
#   ./pipeline.sh path/to/datasheet.md
#
# Optional env vars:
#   AI_DOC_NO_BENCH=1   skip the post-parse benchmark
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: $0 <datasheet.pdf|datasheet.md>" >&2
  exit 2
fi

INPUT="$1"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ ! -e "$INPUT" ]]; then
  echo "[error] input not found: $INPUT" >&2
  exit 1
fi

echo "==> [1/3] parse: $INPUT"
python3 "$SCRIPT_DIR/parse_datasheet.py" "$INPUT"

echo
echo "==> [2/3] source marker"
WORKSPACE="$(cd "$SCRIPT_DIR/../.." && pwd)"
if [[ -f "$WORKSPACE/docs/.source" ]]; then
  echo "    source: $(cat "$WORKSPACE/docs/.source")"
else
  echo "    (no .source marker -- input was a .txt; fallback disabled)"
fi

if [[ "${AI_DOC_NO_BENCH:-}" == "1" ]]; then
  echo
  echo "==> [3/3] benchmark skipped (AI_DOC_NO_BENCH=1)"
  exit 0
fi

echo
echo "==> [3/3] benchmark vs single-file MD"
if [[ -d "$WORKSPACE/docs/topics" && -f "$WORKSPACE/docs/.source" ]]; then
  SRC_MD="$(head -n1 "$WORKSPACE/docs/.source")"
  python3 "$SCRIPT_DIR/bench/bench_md_vs_db.py" \
      --docs "$WORKSPACE/docs" \
      --md "$SRC_MD" || true
else
  echo "    (skip: docs/ or docs/.source not ready)"
fi

echo
echo "==> done"
