"""Windows CI check: print a small booklet to "Microsoft Print to PDF" through the real GDI path."""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pymupdf  # noqa: E402

from booklet_printer.imposition import ImposeOptions, impose  # noqa: E402
from booklet_printer.printing import PrintOptions, list_printers, print_document  # noqa: E402

print("Printers:", list_printers())
src = pymupdf.open()
for i in range(6):
    page = src.new_page()
    page.insert_text((72, 120), f"PAGE {i + 1}", fontsize=40)
result = impose(src, ImposeOptions())
out = Path("printed.pdf").resolve()
out.unlink(missing_ok=True)
for duplex in (True, False):
    warning = print_document(
        result.document,
        PrintOptions(printer="Microsoft Print to PDF", duplex=duplex, copies=2, output_file=str(out)),
    )
    print("duplex", duplex, "warning:", warning)
    for _ in range(60):
        if out.exists() and out.stat().st_size > 0:
            break
        time.sleep(1)
    printed = pymupdf.open(out)
    print("pages printed:", len(printed))
    assert len(printed) == 2 * len(result.document), len(printed)
    printed.close()
    out.unlink()
print("OK")
