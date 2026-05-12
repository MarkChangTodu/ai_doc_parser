"""Convert a PDF to Markdown using the vendored (patched) markitdown.

The vendored copy lives in ``ai_doc_parser/vendor/markitdown/`` and contains
our memory-spool + progress-bar patch on top of upstream.

Usage as CLI:
    python3 convert/pdf_to_md.py <input.pdf> [--out <out.md>] [--force]

Usage as library:
    from convert.pdf_to_md import convert_pdf
    md_path = convert_pdf("IMX8MPRM.pdf", out_path="docs/source/IMX8MPRM.md")

Behaviour:
  * Output is cached by mtime: if <out>.md is newer than the input PDF the
    conversion is skipped (use --force to override).
  * Inserts the vendored markitdown at the FRONT of sys.path so that even if
    upstream markitdown is also pip-installed, the patched version wins.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parents[1]      # ai_doc_parser/
VENDOR_DIR = PKG_ROOT / "vendor"                    # contains markitdown/


def _bootstrap_vendored_markitdown() -> None:
    """Make ``vendor/markitdown/`` importable as ``markitdown``."""
    vendor = str(VENDOR_DIR)
    if vendor not in sys.path:
        sys.path.insert(0, vendor)


def convert_pdf(pdf_path: str | os.PathLike,
                out_path: str | os.PathLike | None = None,
                force: bool = False) -> Path:
    """Convert ``pdf_path`` -> Markdown, return the output Path.

    If ``out_path`` is None, output is ``<pdf_path stem>.md`` next to the PDF.
    Cached by mtime unless ``force`` is True.
    """
    pdf = Path(pdf_path).expanduser().resolve()
    if not pdf.is_file():
        raise FileNotFoundError(pdf)

    out = (Path(out_path).expanduser().resolve()
           if out_path else pdf.with_suffix(".md"))
    out.parent.mkdir(parents=True, exist_ok=True)

    if out.exists() and not force and out.stat().st_mtime >= pdf.stat().st_mtime:
        print(f"[cache] up-to-date: {out}", file=sys.stderr)
        return out

    _bootstrap_vendored_markitdown()
    # Import after bootstrap so we get the vendored patched version.
    from markitdown import MarkItDown  # type: ignore

    print(f"[convert] {pdf}  ->  {out}", file=sys.stderr)
    md = MarkItDown()
    result = md.convert(str(pdf))
    out.write_text(result.markdown, encoding="utf-8")
    print(f"[convert] wrote {out.stat().st_size:,} bytes", file=sys.stderr)
    return out


def _main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("pdf", help="input PDF path")
    p.add_argument("--out", default=None, help="output .md path")
    p.add_argument("--force", action="store_true",
                   help="re-convert even if cached MD is newer")
    args = p.parse_args()

    out = convert_pdf(args.pdf, args.out, args.force)
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
