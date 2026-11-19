"""Page organizer: a grid of page cards (drag and drop) and a page inspector."""

from __future__ import annotations

import tkinter as tk
from tkinter import simpledialog
from typing import TYPE_CHECKING, Callable, Optional

import customtkinter as ctk
import pymupdf as fitz
from PIL import Image, ImageDraw, ImageTk

from ..i18n import t
from ..imposition import mm
from ..pages import PageSpec
from . import render, theme

if TYPE_CHECKING:
    from .app import App

CARD_W = 150
THUMB_H = 150


class PageCard(ctk.CTkFrame):
    def __init__(self, master, organizer: "Organizer"):
        super().__init__(master, corner_radius=12, fg_color=theme.SURFACE, border_width=2,
                         border_color=theme.BORDER, width=CARD_W)
        self.organizer = organizer
        self.index = -1
        self.thumb = ctk.CTkLabel(self, text="", width=CARD_W - 16, height=THUMB_H)
        self.thumb.pack(padx=8, pady=(8, 4))
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=8, pady=(0, 2))
        self.badge = ctk.CTkLabel(row, text="", width=30, height=22, corner_radius=11, fg_color=theme.PRIMARY,
                                  text_color="white", font=theme.font(12, "bold"))
        self.badge.pack(side="left")
        self.source = ctk.CTkLabel(row, text="", font=theme.font(11), text_color=theme.MUTED, anchor="w")
        self.source.pack(side="left", padx=6)
        self.adjust = ctk.CTkLabel(self, text="", font=theme.font(10), text_color=theme.PRIMARY, height=16, anchor="w")
        self.adjust.pack(fill="x", padx=10, pady=(0, 6))
        for w in (self, self.thumb, self.badge, self.source, self.adjust, row):
            self._bind_all(w)

    def _bind_all(self, widget) -> None:
        widget.bind("<ButtonPress-1>", lambda e: self.organizer.press(self, e), add="+")
        widget.bind("<B1-Motion>", lambda e: self.organizer.motion(self, e), add="+")
        widget.bind("<ButtonRelease-1>", lambda e: self.organizer.release(self, e), add="+")
        widget.bind("<Double-Button-1>", lambda e: self.organizer.app.show_in_book(self.index), add="+")
        widget.bind("<Button-3>", lambda e: self.organizer.context_menu(self, e), add="+")

    def set(self, index: int, spec: PageSpec, image: ctk.CTkImage, selected: bool) -> None:
        self.index = index
        self.thumb.configure(image=image)
        self.badge.configure(text=str(index + 1), fg_color=theme.MUTED if spec.is_blank else theme.PRIMARY)
        self.source.configure(text=t("page.blank") if spec.is_blank else t("page.source", n=spec.source + 1))
        self.adjust.configure(text=self.organizer.describe(spec))
        self.set_selected(selected)

    def set_selected(self, selected: bool) -> None:
        self.configure(border_color=theme.PRIMARY if selected else theme.BORDER,
                       fg_color=theme.PRIMARY_SOFT if selected else theme.SURFACE)


class Organizer(ctk.CTkFrame):
    def __init__(self, master, app: "App"):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.cards: list[PageCard] = []
        self.selected: set[int] = set()
        self.anchor = 0
        self._thumbs: dict[tuple, ctk.CTkImage] = {}
        self._drag: Optional[dict] = None
        self._columns = 0
        self._loading = False

        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, columnspan=2, sticky="ew")
        ctk.CTkLabel(head, text=t("org.title"), font=theme.font(20, "bold"), text_color=theme.TEXT).pack(side="left")
        ctk.CTkLabel(head, text=t("org.subtitle"), font=theme.font(12), text_color=theme.MUTED).pack(side="left", padx=12)

        self._build_toolbar()

        self.grid_frame = ctk.CTkScrollableFrame(self, fg_color=theme.SURFACE_2, corner_radius=theme.RADIUS)
        self.grid_frame.grid(row=2, column=0, sticky="nsew")
        self.grid_frame.bind("<Configure>", lambda e: self.app.debounce("reflow", 60, self.reflow))
        self.indicator = tk.Frame(self.grid_frame, width=4, background=theme.pick(theme.ACCENT))

        self._build_inspector()

    # ---------------------------------------------------------------- UI
    def _build_toolbar(self) -> None:
        bar = theme.card(self, height=52)
        bar.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 10))
        inner = ctk.CTkFrame(bar, fg_color="transparent")
        inner.pack(fill="x", padx=8, pady=8)
        self.tool_buttons = []

        def btn(text: str, cmd: Callable[[], None], tip: str, accent: bool = False) -> None:
            icon_only = len(text) <= 2
            b = theme.ghost_button(inner, text=text, command=cmd, width=36 if icon_only else 10,
                                   font=theme.font(16 if icon_only else 12))
            if accent:
                b.configure(text_color=theme.DANGER)
            b.pack(side="left", padx=2)
            Tooltip(b, tip)
            self.tool_buttons.append(b)

        def sep() -> None:
            ctk.CTkFrame(inner, width=1, height=24, fg_color=theme.BORDER).pack(side="left", padx=6)

        btn(t("edit.undo"), self.app.undo, t("tip.undo"))
        btn(t("edit.redo"), self.app.redo, t("tip.redo"))
        sep()
        btn(t("edit.up"), lambda: self.edit(lambda s: self.app.plan.shift(s, -1)), t("tip.up"))
        btn(t("edit.down"), lambda: self.edit(lambda s: self.app.plan.shift(s, 1)), t("tip.down"))
        btn(t("edit.move_to"), self.move_to, t("tip.move_to"))
        sep()
        btn(t("edit.rotate_left"), lambda: self.edit(lambda s: self.app.plan.rotate(s, -90)), t("tip.rotate_left"))
        btn(t("edit.rotate_right"), lambda: self.edit(lambda s: self.app.plan.rotate(s, 90)), t("tip.rotate_right"))
        sep()
        btn(t("edit.blank_before"), lambda: self.edit(lambda s: self.app.plan.insert_blank(min(s) if s else 0)), t("tip.blank_before"))
        btn(t("edit.blank_after"), lambda: self.edit(lambda s: self.app.plan.insert_blank(max(s) + 1 if s else len(self.app.plan))), t("tip.blank_after"))
        btn(t("edit.duplicate"), lambda: self.edit(self.app.plan.duplicate), t("tip.duplicate"))
        btn(t("edit.delete"), lambda: self.edit(self.app.plan.delete), t("tip.delete"), accent=True)
        sep()
        btn(t("edit.restore"), self.app.restore_original, t("tip.restore"))

    def _build_inspector(self) -> None:
        outer = theme.card(self, width=310)
        outer.grid(row=2, column=1, sticky="ns", padx=(12, 0))
        insp = ctk.CTkScrollableFrame(outer, width=290, fg_color="transparent")
        insp.pack(fill="both", expand=True, padx=2, pady=2)
        self.insp_title = ctk.CTkLabel(insp, text=t("insp.none"), font=theme.font(15, "bold"), text_color=theme.TEXT, anchor="w")
        self.insp_title.pack(fill="x", padx=14, pady=(12, 0))
        self.insp_sub = ctk.CTkLabel(insp, text=t("insp.help"), font=theme.font(11), text_color=theme.MUTED,
                                     anchor="w", justify="left", wraplength=270)
        self.insp_sub.pack(fill="x", padx=14)

        holder = ctk.CTkFrame(insp, fg_color=theme.STAGE, corner_radius=10, height=230)
        holder.pack(fill="x", padx=14, pady=8)
        holder.pack_propagate(False)
        self.crop_canvas = tk.Canvas(holder, highlightthickness=0, background=theme.pick(theme.STAGE), cursor="crosshair")
        self.crop_canvas.pack(fill="both", expand=True, padx=4, pady=4)
        self.crop_canvas.bind("<Configure>", lambda e: self.app.debounce("crop", 60, self.render_crop))
        self.crop_canvas.bind("<ButtonPress-1>", self._crop_start)
        self.crop_canvas.bind("<B1-Motion>", self._crop_motion)
        self.crop_canvas.bind("<ButtonRelease-1>", self._crop_end)

        theme.section_title(insp, t("insp.crop")).pack(fill="x", padx=14, pady=(4, 2))
        crop_row = ctk.CTkFrame(insp, fg_color="transparent")
        crop_row.pack(fill="x", padx=14)
        self.crop_entries: list[ctk.CTkEntry] = []
        for i, key in enumerate(("insp.left", "insp.top", "insp.right", "insp.bottom")):
            cell = ctk.CTkFrame(crop_row, fg_color="transparent")
            cell.grid(row=0, column=i, padx=2)
            ctk.CTkLabel(cell, text=t(key), font=theme.font(10), text_color=theme.MUTED).pack()
            e = ctk.CTkEntry(cell, width=58, height=28, corner_radius=8, justify="center")
            e.pack()
            e.bind("<Return>", lambda ev: self.apply_inspector())
            e.bind("<FocusOut>", lambda ev: self.apply_inspector())
            self.crop_entries.append(e)
        ghost = theme.ghost_button(insp, text=t("insp.clear_crop"), height=26, command=self.clear_crop)
        ghost.pack(anchor="w", padx=14, pady=(6, 0))

        theme.section_title(insp, t("insp.size")).pack(fill="x", padx=14, pady=(10, 0))
        self.scale_label = ctk.CTkLabel(insp, text="100 %", font=theme.font(12), text_color=theme.TEXT, anchor="w")
        self.scale_label.pack(fill="x", padx=14)
        self.scale = ctk.CTkSlider(insp, from_=10, to=100, number_of_steps=90, command=self._slider_changed,
                                   progress_color=theme.PRIMARY, button_color=theme.PRIMARY)
        self.scale.pack(fill="x", padx=14)

        theme.section_title(insp, t("insp.position")).pack(fill="x", padx=14, pady=(10, 0))
        self.offset_label = ctk.CTkLabel(insp, text="", font=theme.font(12), text_color=theme.TEXT, anchor="w")
        self.offset_label.pack(fill="x", padx=14)
        self.offx = ctk.CTkSlider(insp, from_=-40, to=40, number_of_steps=80, command=self._slider_changed,
                                  progress_color=theme.SURFACE_2, button_color=theme.PRIMARY)
        self.offx.pack(fill="x", padx=14, pady=(0, 4))
        self.offy = ctk.CTkSlider(insp, from_=-40, to=40, number_of_steps=80, command=self._slider_changed,
                                  progress_color=theme.SURFACE_2, button_color=theme.PRIMARY)
        self.offy.pack(fill="x", padx=14)

        buttons = ctk.CTkFrame(insp, fg_color="transparent")
        buttons.pack(fill="x", padx=14, pady=(14, 12))
        theme.primary_button(buttons, text=t("insp.apply_all"), command=self.apply_to_all).pack(fill="x")
        theme.ghost_button(buttons, text=t("insp.reset"), command=lambda: self.edit(self.app.plan.reset)).pack(fill="x", pady=(6, 0))

    # ------------------------------------------------------------ helpers
    def describe(self, spec: PageSpec) -> str:
        parts = []
        if spec.rotation:
            parts.append(f"↻ {spec.rotation}°")
        if any(spec.crop_mm):
            parts.append(t("adj.crop"))
        if abs(spec.scale - 1) > 1e-9:
            parts.append(f"{round(spec.scale * 100)} %")
        if any(spec.offset_mm):
            parts.append(t("adj.offset"))
        return " · ".join(parts)

    def selection(self) -> list[int]:
        return sorted(i for i in self.selected if 0 <= i < len(self.app.plan))

    def edit(self, op: Callable[[list[int]], list[int]]) -> None:
        if not self.app.src:
            return
        new = op(self.selection())
        self.app.plan_changed(new if new else self.selection())

    def move_to(self) -> None:
        sel = self.selection()
        if not sel:
            return
        n = simpledialog.askinteger(t("edit.move_to"), t("dlg.move_to", count=len(self.app.plan)),
                                    minvalue=1, maxvalue=len(self.app.plan), parent=self)
        if n is None:
            return
        remaining = [i for i in range(len(self.app.plan)) if i not in sel]
        drop = remaining[n - 1] if n - 1 < len(remaining) else len(self.app.plan)
        self.edit(lambda s: self.app.plan.move(s, drop))

    def thumbnail(self, spec: PageSpec) -> ctk.CTkImage:
        opts = self.app.options()
        binding = self.app.result.binding
        key = (spec.source, spec.rotation, spec.crop_mm, spec.scale, spec.offset_mm,
               opts.paper, opts.margin_mm, opts.gutter_mm, binding)
        img = self._thumbs.get(key)
        if img is None:
            half, first, _ = render.half_paper(opts, binding)
            limit_w, limit_h = CARD_W - 16, THUMB_H
            pil = render.booklet_page_image(self.app.src, spec, opts, binding, False, limit_h * 2)
            pil.thumbnail((limit_w * 2, limit_h * 2), Image.Resampling.LANCZOS)
            if spec.is_blank:
                render.draw_center_text(pil, t("page.blank"), scale=1.5)
            w = pil.width / 2
            h = pil.height / 2
            img = ctk.CTkImage(light_image=pil, dark_image=pil, size=(int(w), int(h)))
            self._thumbs[key] = img
        return img

    def clear_cache(self) -> None:
        self._thumbs.clear()

    # ------------------------------------------------------------- refresh
    def refresh(self, select: Optional[list[int]] = None) -> None:
        plan = self.app.plan
        if select is not None:
            self.selected = {i for i in select if 0 <= i < len(plan)}
        self.selected = {i for i in self.selected if i < len(plan)} or ({0} if len(plan) else set())
        while len(self.cards) < len(plan):
            self.cards.append(PageCard(self.grid_frame, self))
        while len(self.cards) > len(plan):
            self.cards.pop().destroy()
        for i, (card, spec) in enumerate(zip(self.cards, plan.pages)):
            card.set(i, spec, self.thumbnail(spec), i in self.selected)
        self._columns = 0
        self.reflow()
        self.load_inspector()

    def reflow(self) -> None:
        width = self.grid_frame.winfo_width()
        cols = max(1, (width - 10) // (CARD_W + 16))
        if cols == self._columns:
            return
        self._columns = cols
        for i, card in enumerate(self.cards):
            card.grid(row=i // cols, column=i % cols, padx=8, pady=8, sticky="n")

    def update_selection_marks(self) -> None:
        for card in self.cards:
            card.set_selected(card.index in self.selected)
        self.load_inspector()

    def select(self, indices: list[int], scroll: bool = True) -> None:
        self.selected = set(indices)
        if indices:
            self.anchor = indices[0]
        self.update_selection_marks()
        if scroll and indices and self.cards and self._columns:
            row = indices[0] // self._columns
            rows = (len(self.cards) + self._columns - 1) // self._columns
            canvas = self.grid_frame._parent_canvas
            canvas.yview_moveto(max(0.0, (row - 0.5) / max(1, rows)))

    # ---------------------------------------------------- mouse: select/drag
    def press(self, card: PageCard, event) -> None:
        ctrl = bool(event.state & 0x0004)
        shift = bool(event.state & 0x0001)
        i = card.index
        if shift:
            lo, hi = sorted((self.anchor, i))
            self.selected = set(range(lo, hi + 1))
        elif ctrl:
            self.selected ^= {i}
            self.anchor = i
        elif i not in self.selected:
            self.selected = {i}
            self.anchor = i
        self._drag = {"card": card, "x": event.x_root, "y": event.y_root, "active": False, "ghost": None,
                      "plain": not (ctrl or shift)}
        self.update_selection_marks()

    def motion(self, card: PageCard, event) -> None:
        d = self._drag
        if not d:
            return
        if not d["active"]:
            if abs(event.x_root - d["x"]) + abs(event.y_root - d["y"]) < 8:
                return
            d["active"] = True
            ghost = tk.Toplevel(self)
            ghost.overrideredirect(True)
            ghost.attributes("-alpha", 0.85) if hasattr(ghost, "attributes") else None
            count = len(self.selection())
            ctk.CTkLabel(ghost, text=t("org.dragging", count=count), fg_color=theme.PRIMARY, text_color="white",
                         corner_radius=10, font=theme.font(12, "bold"), padx=10).pack()
            d["ghost"] = ghost
        d["ghost"].geometry(f"+{event.x_root + 14}+{event.y_root + 10}")
        target = self._target(event.x_root, event.y_root)
        if target is None:
            self.indicator.place_forget()
            return
        idx = target
        if idx < len(self.cards):
            c = self.cards[idx]
            x, y, h = c.winfo_x() - 6, c.winfo_y(), c.winfo_height()
        else:
            c = self.cards[-1]
            x, y, h = c.winfo_x() + c.winfo_width() + 2, c.winfo_y(), c.winfo_height()
        self.indicator.configure(background=theme.pick(theme.ACCENT))
        self.indicator.place(x=x, y=y, height=h)
        self.indicator.lift()
        # auto-scroll
        top = self.grid_frame.winfo_rooty()
        bottom = top + self.grid_frame.winfo_height()
        canvas = self.grid_frame._parent_canvas
        if event.y_root < top + 30:
            canvas.yview_scroll(-1, "units")
        elif event.y_root > bottom - 30:
            canvas.yview_scroll(1, "units")

    def _target(self, x_root: int, y_root: int) -> Optional[int]:
        widget = self.winfo_containing(x_root, y_root)
        while widget is not None and not isinstance(widget, PageCard):
            widget = widget.master
        if widget is None:
            return None
        cx = widget.winfo_rootx() + widget.winfo_width() / 2
        return widget.index + (1 if x_root > cx else 0)

    def release(self, card: PageCard, event) -> None:
        d, self._drag = self._drag, None
        self.indicator.place_forget()
        if not d:
            return
        if d["ghost"] is not None:
            d["ghost"].destroy()
        if not d["active"]:
            if d["plain"]:
                self.select([card.index], scroll=False)
            return
        target = self._target(event.x_root, event.y_root)
        if target is not None:
            sel = self.selection()
            self.edit(lambda _s: self.app.plan.move(sel, target))

    def context_menu(self, card: PageCard, event) -> None:
        if card.index not in self.selected:
            self.select([card.index], scroll=False)
        menu = tk.Menu(self, tearoff=False)
        plan = self.app.plan
        menu.add_command(label=t("menu.show_in_book"), command=lambda: self.app.show_in_book(card.index))
        menu.add_separator()
        menu.add_command(label=t("menu.rotate_left"), command=lambda: self.edit(lambda s: plan.rotate(s, -90)))
        menu.add_command(label=t("menu.rotate_right"), command=lambda: self.edit(lambda s: plan.rotate(s, 90)))
        menu.add_command(label=t("edit.duplicate"), command=lambda: self.edit(plan.duplicate))
        menu.add_command(label=t("edit.blank_before"), command=lambda: self.edit(lambda s: plan.insert_blank(min(s))))
        menu.add_command(label=t("edit.blank_after"), command=lambda: self.edit(lambda s: plan.insert_blank(max(s) + 1)))
        menu.add_command(label=t("insp.reset"), command=lambda: self.edit(plan.reset))
        menu.add_separator()
        menu.add_command(label=t("edit.delete"), command=lambda: self.edit(plan.delete))
        menu.tk_popup(event.x_root, event.y_root)

    # ------------------------------------------------------------ inspector
    def load_inspector(self) -> None:
        sel = self.selection()
        plan = self.app.plan
        self._loading = True
        try:
            if not sel:
                self.insp_title.configure(text=t("insp.none"))
                spec = PageSpec(None)
            else:
                spec = plan[sel[0]]
                if len(sel) == 1:
                    src = t("page.blank") if spec.is_blank else t("page.source", n=spec.source + 1)
                    self.insp_title.configure(text=f"{t('page.booklet', n=sel[0] + 1)} · {src}")
                else:
                    self.insp_title.configure(text=t("insp.multi", count=len(sel)))
            for e, v in zip(self.crop_entries, spec.crop_mm):
                e.delete(0, "end")
                e.insert(0, f"{v:g}")
            self.scale.set(spec.scale * 100)
            self.offx.set(spec.offset_mm[0])
            self.offy.set(spec.offset_mm[1])
            self._update_slider_labels()
        finally:
            self._loading = False
        self.render_crop()

    def _update_slider_labels(self) -> None:
        self.scale_label.configure(text=f"{round(self.scale.get())} %")
        self.offset_label.configure(text=t("insp.offset_value", x=round(self.offx.get()), y=round(self.offy.get())))

    def _slider_changed(self, _value) -> None:
        self._update_slider_labels()
        if not self._loading:
            self.app.debounce("inspector", 300, self.apply_inspector)

    def _entry_values(self) -> tuple[float, float, float, float]:
        vals = []
        for e in self.crop_entries:
            try:
                vals.append(max(0.0, float(e.get().replace(",", "."))))
            except ValueError:
                vals.append(0.0)
        return tuple(vals)  # type: ignore[return-value]

    def apply_inspector(self) -> None:
        sel = self.selection()
        if self._loading or not sel or not self.app.src:
            return
        crop = self._entry_values()
        scale = round(self.scale.get()) / 100
        offset = (float(round(self.offx.get())), float(round(self.offy.get())))
        cur = self.app.plan[sel[0]]
        if len(sel) == 1 and (cur.crop_mm, round(cur.scale, 2), cur.offset_mm) == (crop, round(scale, 2), offset):
            return
        self.app.plan.update(sel, crop_mm=crop, scale=scale, offset_mm=offset)
        self.app.plan_changed(sel)

    def clear_crop(self) -> None:
        sel = self.selection()
        if sel:
            self.app.plan.update(sel, crop_mm=(0.0, 0.0, 0.0, 0.0))
            self.app.plan_changed(sel)

    def apply_to_all(self) -> None:
        sel = self.selection()
        if not sel:
            return
        spec = self.app.plan[sel[0]]
        if spec.is_blank:
            return
        self.app.plan.update(range(len(self.app.plan)), crop_mm=spec.crop_mm, scale=spec.scale,
                             offset_mm=spec.offset_mm, rotation=spec.rotation)
        self.app.plan_changed(sel)
        self.app.toast(t("status.applied_all"))

    # ------------------------------------------------- interactive cropping
    def render_crop(self) -> None:
        c = self.crop_canvas
        c.configure(background=theme.pick(theme.STAGE))
        c.delete("all")
        self._crop_view = None
        sel = self.selection()
        W, H = max(c.winfo_width(), 50), max(c.winfo_height(), 50)
        if not self.app.src or not sel:
            return
        spec = self.app.plan[sel[0]]
        if spec.is_blank:
            c.create_text(W / 2, H / 2, text=t("page.blank"), fill=theme.pick(theme.STAGE_TEXT))
            return
        page = self.app.src[spec.source]
        zoom = min((W - 16) / page.rect.width, (H - 16) / page.rect.height)
        pil = render.pixmap_to_image(page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)).convert("RGBA")
        l, tp, r, b = (mm(v) * zoom for v in spec.crop_mm)
        cx0, cy0 = int(l), int(tp)
        cx1, cy1 = int(pil.width - r), int(pil.height - b)
        if any(spec.crop_mm):
            dim = Image.new("RGBA", pil.size, (15, 15, 30, 150))
            hole = Image.new("L", pil.size, 255)
            ImageDraw.Draw(hole).rectangle((cx0, cy0, cx1, cy1), fill=0)
            pil = Image.composite(Image.alpha_composite(pil, dim), pil, hole)
        self._crop_photo = ImageTk.PhotoImage(pil)
        x0, y0 = (W - pil.width) / 2, (H - pil.height) / 2
        c.create_image(x0, y0, image=self._crop_photo, anchor="nw")
        self._crop_view = (x0, y0, zoom, page.rect)
        c.create_rectangle(x0 + cx0, y0 + cy0, x0 + cx1, y0 + cy1, outline=theme.pick(theme.PRIMARY), width=2)

    def _crop_start(self, event) -> None:
        self._crop_drag = (event.x, event.y) if getattr(self, "_crop_view", None) else None

    def _crop_motion(self, event) -> None:
        if getattr(self, "_crop_drag", None):
            self.crop_canvas.delete("rubber")
            x, y = self._crop_drag
            self.crop_canvas.create_rectangle(x, y, event.x, event.y, outline=theme.pick(theme.ACCENT), width=2,
                                              dash=(4, 2), tags="rubber")

    def _crop_end(self, event) -> None:
        start, self._crop_drag = getattr(self, "_crop_drag", None), None
        if not start or not self._crop_view:
            return
        x0, y0, zoom, rect = self._crop_view
        ax, bx = sorted((start[0], event.x))
        ay, by = sorted((start[1], event.y))
        if bx - ax < 8 or by - ay < 8:
            self.crop_canvas.delete("rubber")
            return
        k = 25.4 / 72.0 / zoom
        crop = (
            max(0.0, (ax - x0) * k),
            max(0.0, (ay - y0) * k),
            max(0.0, (x0 + rect.width * zoom - bx) * k),
            max(0.0, (y0 + rect.height * zoom - by) * k),
        )
        sel = self.selection()
        self.app.plan.update(sel, crop_mm=tuple(round(v, 1) for v in crop))
        self.app.plan_changed(sel)


class Tooltip:
    """Small hover tooltip."""

    def __init__(self, widget, text: str):
        self.widget, self.text, self.tip, self.job = widget, text, None, None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self.hide, add="+")
        widget.bind("<ButtonPress>", self.hide, add="+")

    def _schedule(self, _e=None) -> None:
        self.job = self.widget.after(450, self.show)

    def show(self) -> None:
        if self.tip or not self.widget.winfo_exists():
            return
        x = self.widget.winfo_rootx() + 8
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry(f"+{x}+{y}")
        tk.Label(self.tip, text=self.text, background="#1B1D29", foreground="white", padx=8, pady=4,
                 font=("Segoe UI", 9)).pack()

    def hide(self, _e=None) -> None:
        if self.job:
            self.widget.after_cancel(self.job)
            self.job = None
        if self.tip:
            self.tip.destroy()
            self.tip = None
