import pytest

from booklet_printer.cli import main
from booklet_printer.convert import ConversionError, find_soffice, load_document

pptx = pytest.importorskip("pptx")


def make_pptx(path, n):
    prs = pptx.Presentation()
    for i in range(n):
        slide = prs.slides.add_slide(prs.slide_layouts[5])
        slide.shapes.title.text = f"SLIDE-{i + 1}"
    prs.save(path)


@pytest.mark.skipif(find_soffice() is None, reason="LibreOffice not installed")
def test_pptx_to_booklet(tmp_path):
    src = tmp_path / "deck.pptx"
    make_pptx(src, 5)
    doc = load_document(src)
    assert len(doc) == 5
    out = tmp_path / "out.pdf"
    assert main([str(src), "-o", str(out)]) == 0
    assert out.exists()


def test_unsupported_extension(tmp_path):
    f = tmp_path / "x.txt"
    f.write_text("hi")
    with pytest.raises(ConversionError):
        load_document(f)
