"""Open the app, walk through every view and save screenshots (used by CI and for docs).

Usage: python scripts/ui_screenshots.py OUTPUT_DIR [en|fr] [light|dark]
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

out = Path(sys.argv[1] if len(sys.argv) > 1 else "screenshots")
lang = sys.argv[2] if len(sys.argv) > 2 else "en"
mode = sys.argv[3] if len(sys.argv) > 3 else "light"
os.environ["BOOKLET_LANG"] = lang
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import customtkinter as ctk  # noqa: E402
import pymupdf  # noqa: E402
from PIL import ImageGrab  # noqa: E402

from booklet_printer.ui import theme  # noqa: E402
from booklet_printer.ui.app import App  # noqa: E402

out.mkdir(parents=True, exist_ok=True)
sample = out / "sample.pdf"
doc = pymupdf.open()
colors = [(0.36, 0.36, 0.84), (1, 0.42, 0.29), (0.12, 0.62, 0.42), (0.9, 0.64, 0.09)]
for i in range(10):
    page = doc.new_page(width=595, height=842)
    page.draw_rect(pymupdf.Rect(40, 40, 555, 200), color=None, fill=colors[i % 4])
    page.insert_text((60, 140), f"Chapter {i + 1}", fontsize=44, color=(1, 1, 1))
    for k in range(14):
        page.insert_text((60, 260 + k * 36), "Lorem ipsum dolor sit amet, consectetur adipiscing elit.", fontsize=14)
doc.save(sample)

theme.setup()
ctk.set_appearance_mode(mode)
root = ctk.CTk(fg_color=theme.BG)
root.geometry("1400x860+0+0")
app = App(root)


def snap(name: str) -> None:
    root.update()
    x, y = root.winfo_rootx(), root.winfo_rooty()
    w, h = root.winfo_width(), root.winfo_height()
    try:
        ImageGrab.grab(bbox=(x, y, x + w, y + h)).save(out / f"{lang}-{mode}-{name}.png")
    except Exception as exc:  # noqa: BLE001
        print("screenshot failed:", exc)


steps = [
    (1500, lambda: snap("1-welcome")),
    (100, lambda: app.open_file(str(sample))),
    (2500, lambda: snap("2-book-cover")),
    (100, lambda: app.book.move(1)),
    (1000, lambda: snap("3-book-spread")),
    (100, lambda: app.show_view("sheets")),
    (1200, lambda: snap("4-sheets")),
    (100, lambda: app.show_view("pages")),
    (100, lambda: app.organizer.select([2])),
    (100, lambda: (app.plan.update([2], crop_mm=(10.0, 10.0, 10.0, 60.0)), app.plan_changed([2]))),
    (1500, lambda: snap("5-pages")),
    (100, root.destroy),
]


def run(i: int = 0) -> None:
    if i < len(steps):
        delay, fn = steps[i]
        root.after(delay, lambda: (fn(), run(i + 1)))


run()
root.mainloop()
print("screenshots written to", out)
