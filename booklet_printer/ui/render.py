"""Rendering helpers: PDF pages to PIL images, badges, shadows."""

from __future__ import annotations

from functools import lru_cache
from typing import Optional

import pymupdf as fitz
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from ..imposition import Binding, ImposeOptions, place_page, sheet_geometry
from ..pages import PageSpec
from . import theme


def pixmap_to_image(pix: fitz.Pixmap) -> Image.Image:
    mode = "RGBA" if pix.alpha else "RGB"
    return Image.frombytes(mode, (pix.width, pix.height), pix.samples)


def render_page(page: fitz.Page, height: int) -> Image.Image:
    zoom = max(0.05, height / page.rect.height)
    return pixmap_to_image(page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False))


def render_page_fit(page: fitz.Page, width: int, height: int) -> Image.Image:
    zoom = max(0.05, min(width / page.rect.width, height / page.rect.height))
    return pixmap_to_image(page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False))


def half_paper(opts: ImposeOptions, binding: Binding) -> tuple[fitz.Rect, fitz.Rect, fitz.Rect]:
    """Size of one booklet page (half a sheet) and the content areas for a page
    sitting in the first (left/top) or second (right/bottom) half, in the
    coordinates of that half."""
    sheet, first, second = sheet_geometry(opts, binding)
    if binding == Binding.TOP:
        half = fitz.Rect(0, 0, sheet.width, sheet.height / 2)
        second = fitz.Rect(second.x0, second.y0 - half.height, second.x1, second.y1 - half.height)
    else:
        half = fitz.Rect(0, 0, sheet.width / 2, sheet.height)
        second = fitz.Rect(second.x0 - half.width, second.y0, second.x1 - half.width, second.y1)
    return half, first, second


def booklet_page_image(
    src: fitz.Document,
    spec: Optional[PageSpec],
    opts: ImposeOptions,
    binding: Binding,
    in_second_half: bool,
    height: int,
) -> Image.Image:
    """One page of the booklet as it will look on paper (white page, margins included)."""
    half, first, second = half_paper(opts, binding)
    doc = fitz.open()
    page = doc.new_page(width=half.width, height=half.height)
    place_page(page, src, spec, second if in_second_half else first)
    return render_page(page, height)


@lru_cache(maxsize=16)
def get_font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    names = ["segoeuib.ttf" if bold else "segoeui.ttf", "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
             "Arial Bold.ttf" if bold else "Arial.ttf"]
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # very old Pillow
        return ImageFont.load_default()


def draw_badge(
    img: Image.Image,
    text: str,
    corner: str = "bl",
    color: tuple[int, int, int] = theme.BADGE_BG,
    scale: float = 1.0,
) -> None:
    """Draw a rounded pill with ``text`` in a corner of ``img`` (in place)."""
    draw = ImageDraw.Draw(img)
    size = max(10, int(min(img.width, img.height) * 0.045 * scale))
    fnt = get_font(size, bold=True)
    box = draw.textbbox((0, 0), text, font=fnt)
    tw, th = box[2] - box[0], box[3] - box[1]
    pad_x, pad_y = int(size * 0.6), int(size * 0.35)
    margin = int(size * 0.7)
    w, h = tw + 2 * pad_x, th + 2 * pad_y
    x = margin if corner.endswith("l") else img.width - margin - w
    y = img.height - margin - h if corner.startswith("b") else margin
    draw.rounded_rectangle((x, y, x + w, y + h), radius=h // 2, fill=color)
    draw.text((x + pad_x - box[0], y + pad_y - box[1]), text, font=fnt, fill=theme.BADGE_TEXT)


def draw_center_text(img: Image.Image, text: str, color=(160, 164, 185), scale: float = 1.0) -> None:
    draw = ImageDraw.Draw(img)
    size = max(10, int(min(img.width, img.height) * 0.06 * scale))
    fnt = get_font(size)
    box = draw.textbbox((0, 0), text, font=fnt)
    draw.text(((img.width - (box[2] - box[0])) / 2, (img.height - (box[3] - box[1])) / 2), text, font=fnt, fill=color)


def drop_shadow(size: tuple[int, int], radius: int = 14, offset: tuple[int, int] = (0, 6),
                opacity: int = 90) -> tuple[Image.Image, tuple[int, int]]:
    """A blurred shadow image for a rectangle of ``size``; returns (image, top-left offset)."""
    w, h = size
    pad = radius * 2
    shadow = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rectangle((pad, pad, pad + w, pad + h), fill=(0, 0, 0, opacity))
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius))
    return shadow, (offset[0] - pad, offset[1] - pad)


def spine_shade(size: tuple[int, int], side: str, strength: int = 70) -> Image.Image:
    """Gradient that darkens a page towards the fold. ``side`` is where the fold is."""
    w, h = size
    horizontal = side in ("left", "right")
    length = w if horizontal else h
    band = max(1, int(length * 0.12))
    grad = Image.new("L", (band, 1) if horizontal else (1, band))
    for i in range(band):
        alpha = int(strength * (1 - i / band) ** 2)
        grad.putpixel((i, 0) if horizontal else (0, i), alpha)
    if side == "right":
        grad = grad.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    if side == "bottom":
        grad = grad.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    grad = grad.resize((band, h) if horizontal else (w, band))
    overlay = Image.new("RGBA", size, (0, 0, 0, 0))
    black = Image.new("RGBA", grad.size, (20, 20, 40, 255))
    black.putalpha(grad)
    pos = {"left": (0, 0), "right": (w - band, 0), "top": (0, 0), "bottom": (0, h - band)}[side]
    overlay.paste(black, pos)
    return overlay
