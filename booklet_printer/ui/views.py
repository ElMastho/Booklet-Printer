"""Preview widgets: the flip-book (reading view) and the printed sheets."""

from __future__ import annotations

import tkinter as tk
from typing import TYPE_CHECKING, Optional

import customtkinter as ctk
from PIL import Image, ImageDraw, ImageTk

from ..i18n import t
from ..imposition import Binding, ImposeResult, reading_spreads
from . import render, theme

if TYPE_CHECKING:
    from .app import App

ANIM_FRAMES = 7
ANIM_DELAY = 22  # ms


def position_map(result: ImposeResult) -> dict[int, tuple[int, str]]:
    """Booklet position -> (sheet number, "front"/"back")."""
    out: dict[int, tuple[int, str]] = {}
    for sheet in result.sheets:
        for pos in (sheet.recto.first, sheet.recto.second):
            out[pos] = (sheet.number, "front")
        for pos in (sheet.verso.first, sheet.verso.second):
            out[pos] = (sheet.number, "back")
    return out


class Stage(tk.Canvas):
    """A canvas that follows the light/dark theme."""

    def __init__(self, master, **kw):
        super().__init__(master, highlightthickness=0, background=theme.pick(theme.STAGE), **kw)

    def refresh_colors(self) -> None:
        self.configure(background=theme.pick(theme.STAGE))


class NavBar(ctk.CTkFrame):
    """◀  [slider]  ▶ with a caption."""

    def __init__(self, master, on_move, on_seek):
        super().__init__(master, fg_color="transparent")
        self.on_seek = on_seek
        self.columnconfigure(1, weight=1)
        self.prev = ctk.CTkButton(self, text="‹", width=44, height=44, corner_radius=22, font=theme.font(24, "bold"),
                                  fg_color=theme.PRIMARY, hover_color=theme.PRIMARY_HOVER, command=lambda: on_move(-1))
        self.prev.grid(row=0, column=0, rowspan=2, padx=(0, 12))
        self.caption = ctk.CTkLabel(self, text="", font=theme.font(15, "bold"), text_color=theme.TEXT)
        self.caption.grid(row=0, column=1, sticky="ew")
        self.slider = ctk.CTkSlider(self, from_=0, to=1, number_of_steps=1, command=self._slide,
                                    progress_color=theme.PRIMARY, button_color=theme.PRIMARY,
                                    button_hover_color=theme.PRIMARY_HOVER)
        self.slider.grid(row=1, column=1, sticky="ew", pady=(2, 0))
        self.next = ctk.CTkButton(self, text="›", width=44, height=44, corner_radius=22, font=theme.font(24, "bold"),
                                  fg_color=theme.PRIMARY, hover_color=theme.PRIMARY_HOVER, command=lambda: on_move(1))
        self.next.grid(row=0, column=2, rowspan=2, padx=(12, 0))
        self._count = 1

    def _slide(self, value: float) -> None:
        self.on_seek(int(round(value)))

    def set(self, index: int, count: int, caption: str) -> None:
        self._count = count
        steps = max(1, count - 1)
        self.slider.configure(to=steps, number_of_steps=steps)
        self.slider.set(index)
        self.slider.configure(state="normal" if count > 1 else "disabled")
        self.caption.configure(text=caption)
        self.prev.configure(state="normal" if index > 0 else "disabled")
        self.next.configure(state="normal" if index < count - 1 else "disabled")


class BookView(ctk.CTkFrame):
    """Reading view: the folded booklet, page after page, with page-turn animation."""

    def __init__(self, master, app: "App"):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.index = 0
        self._photo: Optional[ImageTk.PhotoImage] = None
        self._hits: list[tuple[float, float, float, float, int, str]] = []
        self._animating = False
        self._cache: dict[tuple, Image.Image] = {}

        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ctk.CTkLabel(head, text=t("book.title"), font=theme.font(20, "bold"), text_color=theme.TEXT).pack(side="left")
        ctk.CTkLabel(head, text=t("book.subtitle"), font=theme.font(12), text_color=theme.MUTED).pack(side="left", padx=12)

        frame = theme.card(self, fg_color=theme.STAGE, border_width=0)
        frame.grid(row=1, column=0, sticky="nsew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        self.canvas = Stage(frame)
        self.canvas.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        self.canvas.bind("<Configure>", lambda e: self.app.debounce("book", 80, self.render))
        self.canvas.bind("<Button-1>", self._click)
        self.canvas.bind("<Double-Button-1>", self._double_click)

        self.info = ctk.CTkFrame(self, fg_color="transparent")
        self.info.grid(row=2, column=0, sticky="ew", pady=(10, 4))
        self.info.columnconfigure((0, 1), weight=1)
        self.chips = [self._chip(self.info, 0), self._chip(self.info, 1)]

        self.nav = NavBar(self, self.move, self.seek)
        self.nav.grid(row=3, column=0, sticky="ew", pady=(6, 0))

    def _chip(self, master, col: int) -> ctk.CTkLabel:
        lbl = ctk.CTkLabel(master, text="", font=theme.font(12), text_color=theme.TEXT, fg_color=theme.SURFACE,
                           corner_radius=10, height=34, anchor="w", padx=12)
        lbl.grid(row=0, column=col, sticky="ew", padx=4)
        return lbl

    # ------------------------------------------------------------- state
    def spreads(self) -> list[tuple[Optional[int], Optional[int]]]:
        r = self.app.result
        return reading_spreads(r.content_pages) if r else []

    def invalidate(self) -> None:
        self._cache.clear()

    def move(self, delta: int) -> None:
        spreads = self.spreads()
        if not spreads or self._animating:
            return
        new = max(0, min(len(spreads) - 1, self.index + delta))
        if new == self.index:
            return
        self.animate(self.index, new)

    def seek(self, index: int) -> None:
        if index != self.index and not self._animating:
            self.index = index
            self.render()

    # ---------------------------------------------------------- drawing
    def _layout(self) -> tuple[bool, int, int]:
        """(vertical, page width, page height) in pixels for the current canvas."""
        r = self.app.result
        half, _, _ = render.half_paper(self.app.options(), r.binding)
        vertical = r.binding == Binding.TOP
        W, H = max(self.canvas.winfo_width(), 300), max(self.canvas.winfo_height(), 300)
        avail_w, avail_h = W - 60, H - 50
        aspect = half.width / half.height
        if vertical:
            ph = min(avail_h / 2, avail_w / aspect)
        else:
            ph = min(avail_h, (avail_w / 2) / aspect)
        return vertical, max(20, int(ph * aspect)), max(20, int(ph))

    def page_image(self, pos: int, second_half: bool, size: tuple[int, int]) -> Image.Image:
        r = self.app.result
        key = (pos, second_half, size, id(r))
        img = self._cache.get(key)
        if img is None:
            spec = r.spec_at(pos)
            img = render.booklet_page_image(self.app.src, spec, self.app.options(), r.binding, second_half, size[1])
            img = img.resize(size, Image.Resampling.LANCZOS) if img.size != size else img
            if spec is None or spec.is_blank:
                render.draw_center_text(img, t("page.blank"))
            render.draw_badge(img, str(pos + 1), "bl", theme.BADGE_BLANK if spec is None or spec.is_blank else theme.BADGE_BG)
            self._cache[key] = img
        return img

    def _pair(self, index: int) -> tuple[Optional[int], Optional[int]]:
        pair = self.spreads()[index]
        if self.app.result.binding == Binding.RIGHT:
            pair = (pair[1], pair[0])
        return pair

    def compose(self, first: Optional[Image.Image], second: Optional[Image.Image],
                first_scale: float = 1.0, second_scale: float = 1.0,
                under_first: Optional[Image.Image] = None, under_second: Optional[Image.Image] = None
                ) -> tuple[Image.Image, list[tuple[int, int, int, int, str]]]:
        """Draw an open book; returns the image and the page rectangles."""
        vertical, pw, ph = self._layout()
        W, H = max(self.canvas.winfo_width(), 300), max(self.canvas.winfo_height(), 300)
        bg = theme.pick(theme.STAGE)
        img = Image.new("RGBA", (W, H), bg)
        if vertical:
            ox, oy = (W - pw) // 2, (H - 2 * ph) // 2
            slots = [(ox, oy), (ox, oy + ph)]
        else:
            ox, oy = (W - 2 * pw) // 2, (H - ph) // 2
            slots = [(ox, oy), (ox + pw, oy)]
        # Shadow below the visible pages
        present = [i for i, p in enumerate((first or under_first, second or under_second)) if p is not None]
        if present:
            x0 = min(slots[i][0] for i in present)
            y0 = min(slots[i][1] for i in present)
            x1 = max(slots[i][0] + pw for i in present)
            y1 = max(slots[i][1] + ph for i in present)
            shadow, (sx, sy) = render.drop_shadow((x1 - x0, y1 - y0), radius=16, offset=(0, 8), opacity=80)
            img.alpha_composite(shadow, (max(0, x0 + sx), max(0, y0 + sy)))
        rects = []
        fold_sides = ("bottom", "top") if vertical else ("right", "left")
        for i, (page, under, scale) in enumerate(((first, under_first, first_scale), (second, under_second, second_scale))):
            sx, sy = slots[i]
            if under is not None:
                base = under.convert("RGBA")
                base.alpha_composite(render.spine_shade(base.size, fold_sides[i]))
                img.alpha_composite(base, (sx, sy))
            if page is None or scale <= 0.01:
                continue
            page = page.convert("RGBA")
            if scale < 1:
                if vertical:
                    nh = max(1, int(ph * scale))
                    page = page.resize((pw, nh))
                    sy = sy + ph - nh if i == 0 else sy
                else:
                    nw = max(1, int(pw * scale))
                    page = page.resize((nw, ph))
                    sx = sx + pw - nw if i == 0 else sx
                shade = Image.new("RGBA", page.size, (20, 20, 40, int(90 * (1 - scale))))
                page.alpha_composite(shade)
            else:
                page = page.copy()
                page.alpha_composite(render.spine_shade(page.size, fold_sides[i]))
            img.alpha_composite(page, (sx, sy))
            rects.append((sx, sy, sx + page.width, sy + page.height, "first" if i == 0 else "second"))
        # Fold line
        draw = ImageDraw.Draw(img)
        if present and len(present) == 2:
            if vertical:
                draw.line((ox, oy + ph, ox + pw, oy + ph), fill=(120, 120, 140, 160), width=1)
            else:
                draw.line((ox + pw, oy, ox + pw, oy + ph), fill=(120, 120, 140, 160), width=1)
        return img, rects

    def _show(self, img: Image.Image) -> None:
        self._photo = ImageTk.PhotoImage(img)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, image=self._photo, anchor="nw")

    def _images_for(self, index: int) -> tuple[Optional[Image.Image], Optional[Image.Image]]:
        _, pw, ph = self._layout()
        a, b = self._pair(index)
        return (
            self.page_image(a, False, (pw, ph)) if a is not None else None,
            self.page_image(b, True, (pw, ph)) if b is not None else None,
        )

    def render(self) -> None:
        if not self.app.result or self._animating:
            return
        self.canvas.refresh_colors()
        spreads = self.spreads()
        self.index = max(0, min(self.index, len(spreads) - 1))
        first, second = self._images_for(self.index)
        img, rects = self.compose(first, second)
        self._show(img)
        a, b = self._pair(self.index)
        self._hits = []
        for (x0, y0, x1, y1, which) in rects:
            pos = a if which == "first" else b
            self._hits.append((x0, y0, x1, y1, pos, which))
        self._update_info()

    def _update_info(self) -> None:
        r = self.app.result
        spreads = self.spreads()
        n = len(spreads)
        if self.index == 0:
            caption = t("book.cover")
        elif self.index == n - 1:
            caption = t("book.back_cover")
        else:
            lo, hi = spreads[self.index]
            caption = t("book.spread", a=lo + 1, b=hi + 1)
        self.nav.set(self.index, n, caption)
        where = position_map(r)
        for chip, pos in zip(self.chips, self._pair(self.index)):
            if pos is None:
                chip.configure(text="", fg_color="transparent")
                continue
            sheet, side = where[pos]
            spec = r.spec_at(pos)
            if spec is None:
                what = t("book.blank_added")
            elif spec.is_blank:
                what = t("page.blank")
            else:
                what = t("page.source", n=spec.source + 1)
            chip.configure(
                text=t("book.chip", page=pos + 1, what=what, sheet=sheet, side=t(f"side.{side}")),
                fg_color=theme.SURFACE,
            )

    def animate(self, old: int, new: int) -> None:
        """Turn pages: the leading page folds onto the spine, the next one unfolds."""
        if abs(new - old) != 1:
            self.index = new
            self.render()
            return
        self._animating = True
        old_first, old_second = self._images_for(old)
        new_first, new_second = self._images_for(new)
        forward = new > old
        frames = []
        for k in range(1, ANIM_FRAMES + 1):
            s = 1 - k / ANIM_FRAMES
            if forward:  # the second (right) page folds over towards the spine
                frames.append(self.compose(old_first, old_second, 1, s, under_second=new_second)[0])
            else:
                frames.append(self.compose(old_first, old_second, s, 1, under_first=new_first)[0])
        for k in range(1, ANIM_FRAMES + 1):
            s = k / ANIM_FRAMES
            if forward:
                frames.append(self.compose(new_first, new_second, s, 1, under_first=old_first)[0])
            else:
                frames.append(self.compose(new_first, new_second, 1, s, under_second=old_second)[0])

        def step(i: int = 0) -> None:
            if i < len(frames):
                self._show(frames[i])
                self.after(ANIM_DELAY, lambda: step(i + 1))
            else:
                self._animating = False
                self.index = new
                self.render()

        step()

    def _hit(self, event) -> Optional[tuple[int, str]]:
        for x0, y0, x1, y1, pos, which in self._hits:
            if x0 <= event.x <= x1 and y0 <= event.y <= y1:
                return pos, which
        return None

    def _click(self, event) -> None:
        hit = self._hit(event)
        if not hit:
            return
        _, which = hit
        rtl = self.app.result.binding == Binding.RIGHT
        forward = (which == "second") != rtl
        self.move(1 if forward else -1)

    def _double_click(self, event) -> None:
        hit = self._hit(event)
        if hit:
            idx = self.app.result.sequence[hit[0]]
            if idx is not None:
                self.app.open_in_editor(idx)

    def show_position(self, plan_index: int) -> None:
        """Jump to the spread containing a plan page."""
        r = self.app.result
        if not r or plan_index not in r.sequence:
            return
        pos = r.sequence.index(plan_index)
        for i, pair in enumerate(self.spreads()):
            if pos in pair:
                self.index = i
                break
        self.render()


class SheetView(ctk.CTkFrame):
    """The physical sheets: front and back, as they come out of the printer."""

    def __init__(self, master, app: "App"):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.index = 0
        self._photo: Optional[ImageTk.PhotoImage] = None
        self._hits: list[tuple[float, float, float, float, int]] = []

        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew")
        ctk.CTkLabel(head, text=t("sheets.title"), font=theme.font(20, "bold"), text_color=theme.TEXT).pack(side="left")
        self.summary = ctk.CTkLabel(self, text="", font=theme.font(13), text_color=theme.MUTED, anchor="w", justify="left")
        self.summary.grid(row=1, column=0, sticky="ew", pady=(2, 8))

        frame = theme.card(self, fg_color=theme.STAGE, border_width=0)
        frame.grid(row=2, column=0, sticky="nsew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        self.canvas = Stage(frame)
        self.canvas.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        self.canvas.bind("<Configure>", lambda e: self.app.debounce("sheets", 80, self.render))
        self.canvas.bind("<Double-Button-1>", self._double_click)

        self.nav = NavBar(self, self.move, self.seek)
        self.nav.grid(row=3, column=0, sticky="ew", pady=(10, 0))

        guide = theme.card(self)
        guide.grid(row=4, column=0, sticky="ew", pady=(10, 0))
        ctk.CTkLabel(guide, text=t("sheets.guide_title"), font=theme.font(13, "bold"), text_color=theme.TEXT,
                     anchor="w").pack(fill="x", padx=14, pady=(10, 2))
        ctk.CTkLabel(guide, text=t("sheets.guide"), font=theme.font(12), text_color=theme.MUTED, anchor="w",
                     justify="left").pack(fill="x", padx=14, pady=(0, 10))

    def move(self, delta: int) -> None:
        if self.app.result:
            self.seek(max(0, min(len(self.app.result.sheets) - 1, self.index + delta)))

    def seek(self, index: int) -> None:
        if index != self.index:
            self.index = index
            self.render()

    def render(self) -> None:
        r = self.app.result
        if not r:
            return
        self.canvas.refresh_colors()
        self.index = max(0, min(self.index, len(r.sheets) - 1))
        sheet = r.sheets[self.index]
        W, H = max(self.canvas.winfo_width(), 300), max(self.canvas.winfo_height(), 200)
        img = Image.new("RGBA", (W, H), theme.pick(theme.STAGE))
        draw = ImageDraw.Draw(img)
        text_color = theme.pick(theme.STAGE_TEXT)
        title_font = render.get_font(max(12, min(18, W // 60)), bold=True)
        small_font = render.get_font(max(11, min(15, W // 75)))

        front, back = r.document[2 * self.index], r.document[2 * self.index + 1]
        gap = max(150, W // 6)
        avail_w, avail_h = (W - gap - 40) / 2, H - 70
        zoom = min(avail_w / front.rect.width, avail_h / front.rect.height)
        sw, sh = int(front.rect.width * zoom), int(front.rect.height * zoom)
        x_front = (W - 2 * sw - gap) // 2
        x_back = x_front + sw + gap
        y = 40 + (H - 50 - sh) // 2
        _, first, second = render.sheet_geometry(self.app.options(), r.binding)
        self._hits = []
        for page, x, side, key in ((front, x_front, sheet.recto, "front"), (back, x_back, sheet.verso, "back")):
            pimg = render.render_page_fit(page, sw, sh).convert("RGBA")
            for pos, area in ((side.first, first), (side.second, second)):
                spec = r.spec_at(pos)
                blank = spec is None or spec.is_blank
                # badge at the bottom-left of each half
                sub = pimg.crop((int(area.x0 * zoom), int(area.y0 * zoom), int(area.x1 * zoom), int(area.y1 * zoom)))
                if blank:
                    render.draw_center_text(sub, t("page.blank"), scale=1.4)
                render.draw_badge(sub, str(pos + 1), "bl", theme.BADGE_BLANK if blank else theme.BADGE_BG, scale=1.6)
                pimg.paste(sub, (int(area.x0 * zoom), int(area.y0 * zoom)))
                plan_idx = r.sequence[pos]
                if plan_idx is not None:
                    self._hits.append((x + area.x0 * zoom, y + area.y0 * zoom, x + area.x1 * zoom, y + area.y1 * zoom, plan_idx))
            # fold line
            pd = ImageDraw.Draw(pimg)
            if r.binding == Binding.TOP:
                pd.line((0, sh // 2, sw, sh // 2), fill=(170, 170, 190, 255), width=1)
            else:
                pd.line((sw // 2, 0, sw // 2, sh), fill=(170, 170, 190, 255), width=1)
            shadow, (ox, oy) = render.drop_shadow((sw, sh), radius=12, offset=(0, 6), opacity=70)
            img.alpha_composite(shadow, (max(0, x + ox), max(0, y + oy)))
            img.alpha_composite(pimg, (x, y))
            label = t(f"sheets.{key}")
            box = draw.textbbox((0, 0), label, font=title_font)
            draw.text((x + (sw - (box[2] - box[0])) / 2, y - 30), label, font=title_font, fill=text_color)

        # flip arrow between the two sides
        cx, cy = x_front + sw + gap // 2, y + sh // 2
        rr = gap // 4
        draw.arc((cx - rr, cy - rr, cx + rr, cy + rr), start=200, end=520, fill=theme.BADGE_BG, width=4)
        draw.polygon([(cx + rr - 7, cy - 4), (cx + rr + 7, cy - 4), (cx + rr, cy + 8)], fill=theme.BADGE_BG)
        flip = t("sheets.flip")
        for i, line in enumerate(flip.split("\n")):
            box = draw.textbbox((0, 0), line, font=small_font)
            draw.text((cx - (box[2] - box[0]) / 2, cy + rr + 10 + i * (box[3] - box[1] + 4)), line, font=small_font, fill=text_color)

        self._photo = ImageTk.PhotoImage(img)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, image=self._photo, anchor="nw")

        pages = sorted(p + 1 for p in (sheet.recto.first, sheet.recto.second, sheet.verso.first, sheet.verso.second))
        self.summary.configure(text=t("sheets.summary", n=sheet.number, total=len(r.sheets),
                                      pages=", ".join(map(str, pages))))
        self.nav.set(self.index, len(r.sheets), t("sheets.caption", n=sheet.number, total=len(r.sheets)))

    def _double_click(self, event) -> None:
        for x0, y0, x1, y1, idx in self._hits:
            if x0 <= event.x <= x1 and y0 <= event.y <= y1:
                self.app.open_in_editor(idx)
                return
