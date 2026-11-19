import pymupdf as fitz
import pytest

from booklet_printer.imposition import (
    Binding,
    ImposeOptions,
    booklet_sheets,
    impose,
    padded_count,
    page_sequence,
    split_sides,
)


def make_pdf(n, size=(595, 842)):
    doc = fitz.open()
    for i in range(n):
        page = doc.new_page(width=size[0], height=size[1])
        page.insert_text((50, 100), f"PAGE-{i + 1}", fontsize=40)
    return doc


def as_numbers(sheets):
    """1-based page numbers (0 = blank) per side, using the padded sequence."""
    out = []
    for s in sheets:
        out.append(((s.recto.first, s.recto.second), (s.verso.first, s.verso.second)))
    return out


@pytest.mark.parametrize("n,expected", [(1, 4), (4, 4), (5, 8), (8, 8), (9, 12), (16, 16), (17, 20)])
def test_padded_count(n, expected):
    assert padded_count(n) == expected


def test_padded_count_rejects_empty():
    with pytest.raises(ValueError):
        padded_count(0)


def test_eight_pages_left_binding():
    sheets = booklet_sheets(8, Binding.LEFT)
    # 0-based: sheet1 recto 7|0, verso 1|6 ; sheet2 recto 5|2, verso 3|4
    assert as_numbers(sheets) == [((7, 0), (1, 6)), ((5, 2), (3, 4))]


def test_right_binding_is_mirrored():
    left = booklet_sheets(8, Binding.LEFT)
    right = booklet_sheets(8, Binding.RIGHT)
    for l, r in zip(left, right):
        assert (r.recto.first, r.recto.second) == (l.recto.second, l.recto.first)
        assert (r.verso.first, r.verso.second) == (l.verso.second, l.verso.first)


@pytest.mark.parametrize("n", range(1, 41))
@pytest.mark.parametrize("binding", [Binding.LEFT, Binding.RIGHT, Binding.TOP])
def test_every_page_used_once(n, binding):
    sheets = booklet_sheets(n, binding)
    slots = [p for s in sheets for p in (s.recto.first, s.recto.second, s.verso.first, s.verso.second)]
    assert sorted(slots) == list(range(padded_count(n)))
    seq = page_sequence(n)
    assert sorted(p for p in seq if p is not None) == list(range(n))


@pytest.mark.parametrize("n", [4, 8, 12, 20, 36])
def test_spreads_are_consecutive(n):
    """Folded and nested, the sheets must read 1, 2, 3, ... in order."""
    sheets = booklet_sheets(n, Binding.LEFT)
    # Each sheet's verso inner-left/right and recto inner pages surround the
    # centre: the inner spread of the innermost sheet is (n/2 - 1, n/2).
    inner = sheets[-1].verso
    assert (inner.first, inner.second) == (n // 2 - 1, n // 2)
    # Back of the front-cover leaf (verso first) follows the front cover.
    for s in sheets:
        assert s.verso.first == s.recto.second + 1
        assert s.recto.first == s.verso.second + 1


def test_blank_pages_at_end_by_default():
    assert page_sequence(6) == [0, 1, 2, 3, 4, 5, None, None]


def test_keep_back_cover_puts_last_page_last():
    assert page_sequence(6, keep_back_cover=True) == [0, 1, 2, 3, 4, None, None, 5]


def test_impose_output_geometry_portrait_source():
    res = impose(make_pdf(10), ImposeOptions(paper="A4", binding=Binding.AUTO))
    assert res.binding == Binding.LEFT
    assert len(res.document) == 6  # 3 sheets * 2 sides
    assert res.blank_pages == 2
    page = res.document[0]
    assert page.rect.width > page.rect.height  # landscape sheet
    assert round(page.rect.width) == 842 and round(page.rect.height) == 595


def test_impose_auto_top_for_slides():
    res = impose(make_pdf(6, size=(960, 540)), ImposeOptions(binding=Binding.AUTO))
    assert res.binding == Binding.TOP
    page = res.document[0]
    assert page.rect.height > page.rect.width  # portrait sheet, slides stacked


def test_impose_places_right_pages():
    res = impose(make_pdf(8), ImposeOptions(binding=Binding.LEFT, margin_mm=0))
    first = res.document[0]
    w = first.rect.width
    left = first.get_text(clip=fitz.Rect(0, 0, w / 2, first.rect.height))
    right = first.get_text(clip=fitz.Rect(w / 2, 0, w, first.rect.height))
    assert "PAGE-8" in left and "PAGE-1" in right
    verso = res.document[1]
    assert "PAGE-2" in verso.get_text(clip=fitz.Rect(0, 0, w / 2, verso.rect.height))
    assert "PAGE-7" in verso.get_text(clip=fitz.Rect(w / 2, 0, w, verso.rect.height))


def test_split_sides():
    res = impose(make_pdf(8), ImposeOptions(binding=Binding.LEFT))
    rectos, versos = split_sides(res.document, reverse_versos=True)
    assert len(rectos) == len(versos) == 2
    assert "PAGE-4" in versos[0].get_text() and "PAGE-2" in versos[1].get_text()


def test_unknown_paper():
    with pytest.raises(ValueError):
        impose(make_pdf(4), ImposeOptions(paper="B5"))
