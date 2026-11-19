"""Booklet imposition (saddle stitch).

A booklet is made of sheets folded in half and nested. Each sheet carries
four pages: two on the front (recto) and two on the back (verso). With N
pages (N padded to a multiple of 4), sheet ``i`` (0-based) holds, as 0-based
positions in the reading order:

    recto : outer = N-1-2i , inner = 2i
    verso : inner = 2i+1   , outer = N-2-2i

"outer"/"inner" become left/right (binding on the left), right/left
(binding on the right) or top/bottom (binding on the top, "calendar" style,
used for landscape pages such as slides).

Every case is printed duplex with a **flip on the short edge** of the
physical sheet.

The reading order itself comes from a page plan (see :mod:`.pages`), which
lets the user reorder, rotate, crop, scale or blank individual pages.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Sequence

import pymupdf as fitz

from .i18n import t
from .pages import PageSpec

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
        raise ValueError(t("err.no_pages"))
    return max(4, -(-page_count // 4) * 4)


def blank_positions(page_count: int, keep_back_cover: bool = False) -> list[int]:
    """Positions (in the padded sequence) occupied by padding blank pages.

    By default blanks are appended at the end. With ``keep_back_cover`` the
    last page stays on the back cover and blanks are inserted just before it.
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
    """Padded reading order: index in the page plan, or None for padding blanks."""
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


def booklet_sheets(page_count: int, binding: Binding = Binding.LEFT) -> list[Sheet]:
    """Compute the sheets of a saddle-stitched booklet (positions only)."""
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


def reading_spreads(page_count: int) -> list[tuple[Optional[int], Optional[int]]]:
    """Spreads of the folded booklet in reading order, as positions:
    (None, 0) cover, (1, 2), (3, 4) ..., (N-1, None) back cover."""
    n = padded_count(page_count)
    spreads: list[tuple[Optional[int], Optional[int]]] = [(None, 0)]
    spreads += [(i, i + 1) for i in range(1, n - 1, 2)]
    spreads.append((n - 1, None))
    return spreads


# ------------------------------------------------------------------ geometry

@dataclass
class ImposeOptions:
    paper: str = "A4"
    binding: Binding = Binding.AUTO
    margin_mm: float = 5.0  # outer margin around each page area
    gutter_mm: float = 0.0  # extra space on each side of the fold
    keep_back_cover: bool = False
    fold_marks: bool = False


def mm(v: float) -> float:
    return v * 72.0 / 25.4


def sheet_geometry(opts: ImposeOptions, binding: Binding) -> tuple[fitz.Rect, fitz.Rect, fitz.Rect]:
    """Return (sheet rect, first-half area, second-half area)."""
    w, h = PAPER_SIZES[opts.paper]
    m, g = mm(opts.margin_mm), mm(opts.gutter_mm)
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


def content_clip(src_page: fitz.Page, spec: PageSpec) -> fitz.Rect:
    """Visible part of a source page after cropping, in displayed coordinates."""
    r = src_page.rect
    left, top, right, bottom = (mm(v) for v in spec.crop_mm)
    clip = fitz.Rect(r.x0 + left, r.y0 + top, r.x1 - right, r.y1 - bottom)
    if clip.width < 5 or clip.height < 5:  # cropped away: keep a sliver
        clip = fitz.Rect(clip.x0, clip.y0, max(clip.x1, clip.x0 + 5), max(clip.y1, clip.y0 + 5)) & r
    return clip


def content_size(src_page: fitz.Page, spec: PageSpec) -> tuple[float, float]:
    clip = content_clip(src_page, spec)
    if spec.rotation % 180 == 90:
        return clip.height, clip.width
    return clip.width, clip.height


def target_rect(src_page: fitz.Page, spec: PageSpec, area: fitz.Rect) -> fitz.Rect:
    """Where the page lands inside its half-sheet area (fit, scale, offset)."""
    w, h = content_size(src_page, spec)
    f = min(area.width / w, area.height / h) * max(0.1, min(1.0, spec.scale))
    tw, th = w * f, h * f
    dx, dy = mm(spec.offset_mm[0]), mm(spec.offset_mm[1])
    x0 = area.x0 + (area.width - tw) / 2 + dx
    y0 = area.y0 + (area.height - th) / 2 + dy
    # Keep the page inside its area so it never bleeds onto the facing page.
    x0 = min(max(x0, area.x0), area.x1 - tw)
    y0 = min(max(y0, area.y0), area.y1 - th)
    return fitz.Rect(x0, y0, x0 + tw, y0 + th)


def place_page(out_page: fitz.Page, src: fitz.Document, spec: Optional[PageSpec], area: fitz.Rect) -> None:
    if spec is None or spec.is_blank:
        return
    sp = src[spec.source]
    clip = content_clip(sp, spec)
    # show_pdf_page expects the clip in unrotated page coordinates and rotates
    # counter-clockwise; our rotation is clockwise.
    unrotated_clip = clip * sp.derotation_matrix
    out_page.show_pdf_page(
        target_rect(sp, spec, area), src, spec.source, clip=unrotated_clip, rotate=-spec.rotation
    )


def resolve_binding(src: fitz.Document, plan: Sequence[PageSpec], binding: Binding) -> Binding:
    if binding != Binding.AUTO:
        return binding
    real = [p for p in plan if not p.is_blank]
    if not real:
        return Binding.LEFT
    landscape = 0
    for p in real:
        w, h = content_size(src[p.source], p)
        landscape += w > h
    return Binding.TOP if landscape * 2 > len(real) else Binding.LEFT


def _fold_marks(page: fitz.Page, binding: Binding) -> None:
    r = page.rect
    length = mm(4)
    color = (0.5, 0.5, 0.5)
    if binding == Binding.TOP:
        y = r.height / 2
        page.draw_line((0, y), (length, y), color=color, width=0.5)
        page.draw_line((r.width - length, y), (r.width, y), color=color, width=0.5)
    else:
        x = r.width / 2
        page.draw_line((x, 0), (x, length), color=color, width=0.5)
        page.draw_line((x, r.height - length), (x, r.height), color=color, width=0.5)


# --------------------------------------------------------------- imposition

@dataclass
class ImposeResult:
    document: fitz.Document  # recto, verso, recto, verso...
    sheets: list[Sheet]
    binding: Binding
    plan: list[PageSpec]
    sequence: list[Optional[int]]  # position -> plan index (None = padding blank)
    content_pages: int  # pages in the plan (including blanks inserted by the user)
    padding_pages: int  # blanks added to reach a multiple of 4

    def spec_at(self, position: int) -> Optional[PageSpec]:
        idx = self.sequence[position]
        return None if idx is None else self.plan[idx]


def impose(
    src: fitz.Document,
    opts: Optional[ImposeOptions] = None,
    plan: Optional[Sequence[PageSpec]] = None,
) -> ImposeResult:
    """Build the imposed PDF (one output page per sheet side)."""
    opts = opts or ImposeOptions()
    if opts.paper not in PAPER_SIZES:
        raise ValueError(t("err.unknown_paper", paper=opts.paper))
    specs = list(plan) if plan is not None else [PageSpec(i) for i in range(len(src))]
    binding = resolve_binding(src, specs, opts.binding)
    sheets = booklet_sheets(len(specs), binding)
    seq = page_sequence(len(specs), opts.keep_back_cover)
    sheet_rect, first, second = sheet_geometry(opts, binding)

    def spec(pos: int) -> Optional[PageSpec]:
        return None if seq[pos] is None else specs[seq[pos]]

    out = fitz.open()
    for sheet in sheets:
        for side in (sheet.recto, sheet.verso):
            page = out.new_page(width=sheet_rect.width, height=sheet_rect.height)
            place_page(page, src, spec(side.first), first)
            place_page(page, src, spec(side.second), second)
            if opts.fold_marks:
                _fold_marks(page, binding)
    return ImposeResult(
        document=out,
        sheets=sheets,
        binding=binding,
        plan=specs,
        sequence=seq,
        content_pages=len(specs),
        padding_pages=padded_count(len(specs)) - len(specs),
    )


def render_reading_order(src: fitz.Document, plan: Sequence[PageSpec], opts: ImposeOptions) -> fitz.Document:
    """The edited document, one page per booklet page (half-sheet size).

    Useful to export the result of the page editor as a normal PDF.
    """
    binding = resolve_binding(src, plan, opts.binding)
    _, first, _ = sheet_geometry(opts, binding)
    out = fitz.open()
    area = fitz.Rect(0, 0, first.width, first.height)
    for spec in plan:
        page = out.new_page(width=area.width, height=area.height)
        place_page(page, src, spec, area)
    return out


def split_sides(imposed: fitz.Document, reverse_backs: bool = False) -> tuple[fitz.Document, fitz.Document]:
    """Split an imposed document into fronts and backs (manual duplex)."""
    fronts, backs = fitz.open(), fitz.open()
    for i in range(0, len(imposed), 2):
        fronts.insert_pdf(imposed, from_page=i, to_page=i)
    back_idx = list(range(1, len(imposed), 2))
    if reverse_backs:
        back_idx.reverse()
    for i in back_idx:
        backs.insert_pdf(imposed, from_page=i, to_page=i)
    return fronts, backs
