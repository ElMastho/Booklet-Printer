"""Booklet imposition (saddle stitch).

A booklet is made of sheets folded in half and nested. Each sheet carries
four pages: two on the front (recto) and two on the back (verso). With N
pages (N padded to a multiple of 4), sheet ``i`` (0-based) holds, in 0-based
page indexes:

    recto : outer = N-1-2i , inner = 2i
    verso : inner = 2i+1   , outer = N-2-2i

"outer"/"inner" become left/right (binding on the left), right/left
(binding on the right) or top/bottom (binding on the top, "calendar" style,
used for landscape pages such as slides).

Every case is printed duplex with a **flip on the short edge** of the
physical sheet.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

import pymupdf as fitz

# Paper sizes in PostScript points (1/72 inch), portrait orientation.
PAPER_SIZES: dict[str, tuple[float, float]] = {
    "A4": (595.28, 841.89),
    "A3": (841.89, 1190.55),
    "Letter": (612.0, 792.0),
    "Legal": (612.0, 1008.0),
    "Tabloid": (792.0, 1224.0),
}

BLANK = None  # marker for a padding page


class Binding(str, Enum):
    LEFT = "left"  # classic western booklet
    RIGHT = "right"  # right-to-left reading (manga, arabic, hebrew...)
    TOP = "top"  # calendar style, best for landscape pages (slides)
    AUTO = "auto"  # TOP if most pages are landscape, else LEFT


@dataclass(frozen=True)
class Side:
    """One side of a sheet: positions in the padded reading sequence
    (see ``page_sequence``) shown in the first and second half.

    For LEFT/RIGHT bindings the halves are left/right; for TOP binding they
    are top/bottom.
    """

    first: int
    second: int


@dataclass(frozen=True)
class Sheet:
    number: int  # 1-based
    recto: Side
    verso: Side


def padded_count(page_count: int) -> int:
    """Smallest multiple of 4 that is >= page_count (and >= 4)."""
    if page_count <= 0:
        raise ValueError("Le document ne contient aucune page.")
    return max(4, -(-page_count // 4) * 4)


def blank_positions(page_count: int, keep_back_cover: bool = False) -> list[int]:
    """Positions (in the padded sequence) occupied by blank pages.

    By default blanks are appended at the end. With ``keep_back_cover`` the
    last source page stays on the back cover and blanks are inserted just
    before it.
    """
    total = padded_count(page_count)
    missing = total - page_count
    if missing == 0:
        return []
    if keep_back_cover and page_count >= 2:
        start = page_count - 1
        return list(range(start, start + missing))
    return list(range(page_count, total))


def page_sequence(page_count: int, keep_back_cover: bool = False) -> list[Optional[int]]:
    """Padded reading order: source page index or None for blank pages."""
    total = padded_count(page_count)
    blanks = set(blank_positions(page_count, keep_back_cover))
    seq: list[Optional[int]] = []
    src = 0
    for pos in range(total):
        if pos in blanks:
            seq.append(BLANK)
        else:
            seq.append(src)
            src += 1
    return seq


def booklet_sheets(
    page_count: int,
    binding: Binding = Binding.LEFT,
    keep_back_cover: bool = False,
) -> list[Sheet]:
    """Compute the sheets of a saddle-stitched booklet.

    ``keep_back_cover`` is accepted for symmetry; positions do not depend on it
    (use ``page_sequence`` to map positions to source pages).
    """
    n = padded_count(page_count)
    sheets: list[Sheet] = []
    for i in range(n // 4):
        rec_outer, rec_inner = n - 1 - 2 * i, 2 * i
        ver_inner, ver_outer = 2 * i + 1, n - 2 - 2 * i
        if binding == Binding.RIGHT:
            # Reading right to left: the first page is on the right of a spread.
            recto = Side(rec_inner, rec_outer)
            verso = Side(ver_outer, ver_inner)
        else:
            # LEFT: left/right ; TOP: top/bottom (same logic rotated 90°).
            recto = Side(rec_outer, rec_inner)
            verso = Side(ver_inner, ver_outer)
        sheets.append(Sheet(i + 1, recto, verso))
    return sheets


def resolve_binding(doc: fitz.Document, binding: Binding) -> Binding:
    if binding != Binding.AUTO:
        return binding
    landscape = sum(1 for p in doc if p.rect.width > p.rect.height)
    return Binding.TOP if landscape * 2 > len(doc) else Binding.LEFT


@dataclass
class ImposeOptions:
    paper: str = "A4"
    binding: Binding = Binding.AUTO
    margin_mm: float = 5.0  # outer margin around each page area
    gutter_mm: float = 0.0  # extra space on each side of the fold
    keep_back_cover: bool = False
    fold_marks: bool = False


def _mm(v: float) -> float:
    return v * 72.0 / 25.4


def sheet_geometry(opts: ImposeOptions, binding: Binding) -> tuple[fitz.Rect, fitz.Rect, fitz.Rect]:
    """Return (sheet rect, first-half area, second-half area)."""
    w, h = PAPER_SIZES[opts.paper]
    m, g = _mm(opts.margin_mm), _mm(opts.gutter_mm)
    if binding == Binding.TOP:
        sheet = fitz.Rect(0, 0, w, h)  # portrait sheet, halves stacked
        mid = h / 2
        first = fitz.Rect(m, m, w - m, mid - g)
        second = fitz.Rect(m, mid + g, w - m, h - m)
    else:
        sheet = fitz.Rect(0, 0, h, w)  # landscape sheet, halves side by side
        mid = h / 2
        first = fitz.Rect(m, m, mid - g, w - m)
        second = fitz.Rect(mid + g, m, h - m, w - m)
    return sheet, first, second


def _place(out_page: fitz.Page, src: fitz.Document, index: Optional[int], area: fitz.Rect) -> None:
    if index is None:
        return
    # show_pdf_page keeps proportions and centers the page inside the area.
    out_page.show_pdf_page(area, src, index)


def _fold_marks(page: fitz.Page, binding: Binding) -> None:
    r = page.rect
    length = _mm(4)
    color = (0.5, 0.5, 0.5)
    if binding == Binding.TOP:
        y = r.height / 2
        page.draw_line((0, y), (length, y), color=color, width=0.5)
        page.draw_line((r.width - length, y), (r.width, y), color=color, width=0.5)
    else:
        x = r.width / 2
        page.draw_line((x, 0), (x, length), color=color, width=0.5)
        page.draw_line((x, r.height - length), (x, r.height), color=color, width=0.5)


@dataclass
class ImposeResult:
    document: fitz.Document  # recto, verso, recto, verso...
    sheets: list[Sheet]
    binding: Binding
    source_pages: int
    blank_pages: int


def impose(src: fitz.Document, opts: Optional[ImposeOptions] = None) -> ImposeResult:
    """Build the imposed PDF (one output page per sheet side)."""
    opts = opts or ImposeOptions()
    if opts.paper not in PAPER_SIZES:
        raise ValueError(f"Format de papier inconnu : {opts.paper}")
    binding = resolve_binding(src, opts.binding)
    sheets = booklet_sheets(len(src), binding, opts.keep_back_cover)
    seq = page_sequence(len(src), opts.keep_back_cover)
    sheet_rect, first, second = sheet_geometry(opts, binding)

    out = fitz.open()
    for sheet in sheets:
        for side in (sheet.recto, sheet.verso):
            page = out.new_page(width=sheet_rect.width, height=sheet_rect.height)
            _place(page, src, seq[side.first], first)
            _place(page, src, seq[side.second], second)
            if opts.fold_marks:
                _fold_marks(page, binding)
    return ImposeResult(
        document=out,
        sheets=sheets,
        binding=binding,
        source_pages=len(src),
        blank_pages=padded_count(len(src)) - len(src),
    )


def split_sides(imposed: fitz.Document, reverse_versos: bool = False) -> tuple[fitz.Document, fitz.Document]:
    """Split an imposed document into rectos and versos (manual duplex)."""
    rectos, versos = fitz.open(), fitz.open()
    for i in range(0, len(imposed), 2):
        rectos.insert_pdf(imposed, from_page=i, to_page=i)
    verso_idx = list(range(1, len(imposed), 2))
    if reverse_versos:
        verso_idx.reverse()
    for i in verso_idx:
        versos.insert_pdf(imposed, from_page=i, to_page=i)
    return rectos, versos
