import pymupdf as fitz
import pytest

from booklet_printer.imposition import Binding, ImposeOptions, impose, render_reading_order
from booklet_printer.pages import PagePlan, PageSpec, parse_page_list


def sources(plan):
    return [p.source for p in plan.pages]


def make_pdf(n, size=(595, 842)):
    doc = fitz.open()
    for i in range(n):
        page = doc.new_page(width=size[0], height=size[1])
        page.insert_text((60, 120), f"PAGE-{i + 1}", fontsize=40)
    return doc


def test_move_forward_and_back():
    plan = PagePlan.from_count(6)
    assert plan.move([0], 3) == [2]
    assert sources(plan) == [1, 2, 0, 3, 4, 5]
    plan.move([4, 5], 0)
    assert sources(plan) == [4, 5, 1, 2, 0, 3]


def test_shift_and_bounds():
    plan = PagePlan.from_count(4)
    assert plan.shift([0], -1) == [0]
    assert plan.shift([1], 1) == [2]
    assert sources(plan) == [0, 2, 1, 3]
    plan.shift([3], 5)
    assert sources(plan) == [0, 2, 1, 3]


def test_delete_never_empties():
    plan = PagePlan.from_count(3)
    assert plan.delete([0, 1, 2]) == []
    assert len(plan) == 3
    plan.delete([1])
    assert sources(plan) == [0, 2]


def test_duplicate_blank_rotate_reverse():
    plan = PagePlan.from_count(3)
    plan.duplicate([1])
    assert sources(plan) == [0, 1, 1, 2]
    plan.insert_blank(0, 2)
    assert sources(plan) == [None, None, 0, 1, 1, 2]
    plan.rotate([2], -90)
    assert plan[2].rotation == 270
    plan.reverse([2, 3, 4, 5])
    assert sources(plan) == [None, None, 2, 1, 1, 0]


def test_undo_redo():
    plan = PagePlan.from_count(4)
    plan.move([3], 0)
    plan.delete([0])
    assert sources(plan) == [0, 1, 2]
    assert plan.undo() and sources(plan) == [3, 0, 1, 2]
    assert plan.undo() and sources(plan) == [0, 1, 2, 3]
    assert not plan.undo()
    assert plan.redo() and sources(plan) == [3, 0, 1, 2]
    plan.rotate([0], 90)
    assert not plan.can_redo


def test_update_clamps_and_skips_blanks():
    plan = PagePlan.from_count(2)
    plan.insert_blank(1)
    plan.update([0, 1, 2], scale=5, crop_mm=(1, 2, 3, 4))
    assert plan[0].scale == 1.0 and plan[0].crop_mm == (1, 2, 3, 4)
    assert plan[1].is_blank and not plan[1].is_adjusted
    plan.reset([0])
    assert not plan[0].is_adjusted


def test_parse_page_list():
    specs = parse_page_list("3-1, blank, 5-, 2:r90", 6)
    assert [s.source for s in specs] == [2, 1, 0, None, 4, 5, 1]
    assert specs[-1].rotation == 90
    with pytest.raises(ValueError):
        parse_page_list("9", 6)
    with pytest.raises(ValueError):
        parse_page_list("1:r45", 6)


def test_impose_follows_plan_order():
    src = make_pdf(4)
    plan = [PageSpec(3), PageSpec(1), PageSpec(2), PageSpec(0)]
    res = impose(src, ImposeOptions(binding=Binding.LEFT, margin_mm=0), plan)
    front = res.document[0]
    w, h = front.rect.width, front.rect.height
    # Front of sheet 1: last page (orig 1) on the left, first page (orig 4) on the right
    assert "PAGE-1" in front.get_text(clip=fitz.Rect(0, 0, w / 2, h))
    assert "PAGE-4" in front.get_text(clip=fitz.Rect(w / 2, 0, w, h))


def test_user_blank_and_padding():
    src = make_pdf(3)
    plan = [PageSpec(0), PageSpec(None), PageSpec(1), PageSpec(2), PageSpec(None)]
    res = impose(src, ImposeOptions(), plan)
    assert res.content_pages == 5 and res.padding_pages == 3
    assert len(res.document) == 4


def test_rotation_and_crop_are_applied():
    src = make_pdf(1)
    spec = PageSpec(0, rotation=90)
    res = impose(src, ImposeOptions(binding=Binding.LEFT), [spec])
    words = res.document[0].get_text("words")
    assert any(w[4] == "PAGE-1" for w in words)
    # Crop away everything but the bottom half: the text (near the top) disappears
    cropped = PageSpec(0, crop_mm=(0, 150, 0, 0))
    res = impose(src, ImposeOptions(binding=Binding.LEFT), [cropped])
    assert "PAGE-1" not in res.document[0].get_text()


def test_scale_and_offset_stay_inside_area():
    src = make_pdf(1)
    spec = PageSpec(0, scale=0.5, offset_mm=(500, -500))
    res = impose(src, ImposeOptions(binding=Binding.LEFT, margin_mm=0), [spec])
    page = res.document[0]
    for b in page.get_text("blocks"):
        assert b[0] >= page.rect.width / 2 - 1  # stays in the right half (first page)


def test_render_reading_order():
    src = make_pdf(3)
    out = render_reading_order(src, [PageSpec(2), PageSpec(None), PageSpec(0)], ImposeOptions())
    assert len(out) == 3
    assert "PAGE-3" in out[0].get_text() and out[1].get_text().strip() == ""
