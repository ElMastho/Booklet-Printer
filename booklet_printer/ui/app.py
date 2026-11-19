"""Main window."""

from __future__ import annotations

import sys
import tempfile
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Callable, Optional

import customtkinter as ctk
import pymupdf as fitz

from .. import REPO, __version__, updater
from ..config import get_setting, set_setting
from ..convert import SUPPORTED_EXTENSIONS, load_document
from ..i18n import LANGUAGES, set_language, t
from ..imposition import PAPER_SIZES, Binding, ImposeOptions, ImposeResult, impose, render_reading_order, split_sides
from ..pages import PagePlan
from ..printing import PrintOptions, default_printer, list_printers, print_document
from . import theme
from .organizer import Organizer
from .views import BookView, SheetView

BINDINGS = [Binding.AUTO, Binding.LEFT, Binding.RIGHT, Binding.TOP]
VIEWS = ("book", "pages", "sheets")
APPEARANCES = ("system", "light", "dark")


class App(ctk.CTkFrame):
    def __init__(self, master: ctk.CTk, initial: Optional[str] = None, state: Optional[dict] = None):
        super().__init__(master, fg_color=theme.BG, corner_radius=0)
        self.master = master
        self.src: Optional[fitz.Document] = None
        self.src_path: Optional[Path] = None
        self.plan = PagePlan()
        self.result: Optional[ImposeResult] = None
        self._jobs: dict[str, str] = {}
        self._progress_text: Optional[str] = None
        self._toast_job: Optional[str] = None
        self.view = "book"
        self.pack(fill="both", expand=True)
        master.title(f"Booklet Printer {__version__}")

        self._make_vars((state or {}).get("vars", {}))
        self._build()
        self._bind_keys()

        if state and state.get("src") is not None:
            self.src, self.src_path, self.plan = state["src"], state["src_path"], state["plan"]
            self.view = state.get("view", "book")
            self.after(30, lambda: self._document_ready(state.get("selection", [0])))
        else:
            self.show_view("welcome")
            if initial:
                self.after(150, lambda: self.open_file(initial))
            if updater.is_frozen_windows() and get_setting("auto_update", True):
                self.after(2000, lambda: self.check_updates(silent=True))

    # ================================================================ state
    def _make_vars(self, v: dict) -> None:
        self.paper = ctk.StringVar(value=v.get("paper", get_setting("paper", "A4")))
        self.binding = Binding(v.get("binding", Binding.AUTO.value))
        self.margin = ctk.DoubleVar(value=v.get("margin", 5.0))
        self.gutter = ctk.DoubleVar(value=v.get("gutter", 0.0))
        self.back_cover = ctk.BooleanVar(value=v.get("back_cover", False))
        self.fold_marks = ctk.BooleanVar(value=v.get("fold_marks", False))
        self.printer = ctk.StringVar(value=v.get("printer", ""))
        self.copies = ctk.StringVar(value=str(v.get("copies", 1)))
        self.auto_duplex = ctk.BooleanVar(value=v.get("auto_duplex", get_setting("auto_duplex", True)))
        self.reverse_backs = ctk.BooleanVar(value=v.get("reverse_backs", False))

    def _export_state(self) -> dict:
        return {
            "src": self.src,
            "src_path": self.src_path,
            "plan": self.plan,
            "selection": self.organizer.selection() if self.src else [0],
            "view": self.view,
            "vars": {
                "paper": self.paper.get(),
                "binding": self.binding.value,
                "margin": self.margin.get(),
                "gutter": self.gutter.get(),
                "back_cover": self.back_cover.get(),
                "fold_marks": self.fold_marks.get(),
                "printer": self.printer.get(),
                "copies": self._copies(),
                "auto_duplex": self.auto_duplex.get(),
                "reverse_backs": self.reverse_backs.get(),
            },
        }

    def options(self) -> ImposeOptions:
        return ImposeOptions(
            paper=self.paper.get(),
            binding=self.binding,
            margin_mm=round(self.margin.get()),
            gutter_mm=round(self.gutter.get()),
            keep_back_cover=self.back_cover.get(),
            fold_marks=self.fold_marks.get(),
        )

    def _copies(self) -> int:
        try:
            return max(1, min(999, int(self.copies.get())))
        except ValueError:
            return 1

    def debounce(self, name: str, delay: int, func: Callable[[], None]) -> None:
        if name in self._jobs:
            self.after_cancel(self._jobs[name])
        self._jobs[name] = self.after(delay, lambda: (self._jobs.pop(name, None), func()))

    # =================================================================== UI
    def _build(self) -> None:
        self._build_header()
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=16, pady=(0, 16))
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)

        self.main = ctk.CTkFrame(body, fg_color="transparent")
        self.main.grid(row=0, column=0, sticky="nsew")
        self.main.columnconfigure(0, weight=1)
        self.main.rowconfigure(1, weight=1)

        self.switcher = ctk.CTkSegmentedButton(
            self.main,
            values=[t("tab.book"), t("tab.pages"), t("tab.sheets")],
            command=self._switch,
            height=38,
            corner_radius=12,
            font=theme.font(13, "bold"),
            selected_color=theme.SELECTED,
            selected_hover_color=theme.SELECTED_HOVER,
            unselected_color=theme.SURFACE,
            unselected_hover_color=theme.PRIMARY_SOFT,
            fg_color=theme.SURFACE,
            text_color=(theme.TEXT[0], theme.TEXT[1]),
        )
        self.switcher.grid(row=0, column=0, sticky="w", pady=(0, 12))

        self.stack = ctk.CTkFrame(self.main, fg_color="transparent")
        self.stack.grid(row=1, column=0, sticky="nsew")
        self.stack.columnconfigure(0, weight=1)
        self.stack.rowconfigure(0, weight=1)
        self.book = BookView(self.stack, self)
        self.organizer = Organizer(self.stack, self)
        self.sheets = SheetView(self.stack, self)
        self.welcome = self._build_welcome(self.stack)
        for frame in (self.book, self.organizer, self.sheets, self.welcome):
            frame.grid(row=0, column=0, sticky="nsew")

        side = ctk.CTkFrame(body, fg_color="transparent", width=330)
        side.grid(row=0, column=1, sticky="ns", padx=(16, 0))
        side.rowconfigure(0, weight=1)
        self.panel = ctk.CTkScrollableFrame(side, width=300, fg_color="transparent")
        self.panel.grid(row=0, column=0, sticky="nsew")
        actions = theme.card(side, border_color=theme.PRIMARY_SOFT, border_width=2)
        actions.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        self._build_panel(self.panel, actions)

        self.toast_label = ctk.CTkLabel(self, text="", fg_color=theme.TEXT, text_color=theme.BG, corner_radius=12,
                                        font=theme.font(12, "bold"), height=36, padx=16)

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, fg_color=theme.SURFACE, corner_radius=0, height=68)
        header.pack(fill="x", pady=(0, 16))
        header.pack_propagate(False)
        logo = ctk.CTkLabel(header, text="B", width=40, height=40, corner_radius=12, fg_color=theme.PRIMARY,
                            text_color="white", font=theme.font(20, "bold"))
        logo.pack(side="left", padx=(18, 10))
        titles = ctk.CTkFrame(header, fg_color="transparent")
        titles.pack(side="left")
        ctk.CTkLabel(titles, text="Booklet Printer", font=theme.font(17, "bold"), text_color=theme.TEXT,
                     anchor="w").pack(anchor="w")
        self.file_label = ctk.CTkLabel(titles, text=t("label.no_file"), font=theme.font(12), text_color=theme.MUTED,
                                       anchor="w")
        self.file_label.pack(anchor="w")

        right = ctk.CTkFrame(header, fg_color="transparent")
        right.pack(side="right", padx=18)
        lang_values = [t("menu.lang_auto")] + list(LANGUAGES.values())
        codes = ["auto"] + list(LANGUAGES)
        current = get_setting("language", "auto")
        self.lang_menu = ctk.CTkOptionMenu(
            right, values=lang_values, width=120, corner_radius=10,
            command=lambda v: self.change_language(codes[lang_values.index(v)]),
            fg_color=theme.SURFACE_2, button_color=theme.SURFACE_2, button_hover_color=theme.PRIMARY_SOFT,
            text_color=theme.TEXT, dropdown_font=theme.font(12), font=theme.font(12),
        )
        self.lang_menu.set(lang_values[codes.index(current)] if current in codes else lang_values[0])
        self.lang_menu.pack(side="left", padx=4)
        app_values = [t(f"appearance.{a}") for a in APPEARANCES]
        self.appearance = ctk.CTkOptionMenu(
            right, values=app_values, width=120, corner_radius=10,
            command=lambda v: self.change_appearance(APPEARANCES[app_values.index(v)]),
            fg_color=theme.SURFACE_2, button_color=theme.SURFACE_2, button_hover_color=theme.PRIMARY_SOFT,
            text_color=theme.TEXT, dropdown_font=theme.font(12), font=theme.font(12),
        )
        self.appearance.set(app_values[APPEARANCES.index(get_setting("appearance", "system"))])
        self.appearance.pack(side="left", padx=4)
        more = theme.ghost_button(right, text="•••", width=44, height=28, font=theme.font(12, "bold"))
        more.configure(command=lambda: self._more_popup(more))
        more.pack(side="left", padx=4)
        theme.primary_button(right, text=t("btn.open"), command=self.ask_open, width=150).pack(side="left", padx=(10, 0))

    def _more_popup(self, button) -> None:
        menu = tk.Menu(self, tearoff=False)
        menu.add_command(label=t("menu.how_to"), command=lambda: messagebox.showinfo(t("menu.how_to"), t("help.long")))
        menu.add_command(label=t("menu.check_updates"), command=lambda: self.check_updates(silent=False))
        auto = tk.BooleanVar(value=get_setting("auto_update", True))
        menu.add_checkbutton(label=t("menu.auto_update"), variable=auto,
                             command=lambda: set_setting("auto_update", bool(auto.get())))
        menu.add_separator()
        menu.add_command(label=t("menu.about"),
                         command=lambda: messagebox.showinfo(t("menu.about"), t("dlg.about", version=__version__, repo=REPO)))
        menu.tk_popup(button.winfo_rootx(), button.winfo_rooty() + button.winfo_height() + 4)

    def _build_welcome(self, master) -> ctk.CTkFrame:
        outer = ctk.CTkFrame(master, fg_color="transparent")
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(0, weight=1)
        box = theme.card(outer, border_width=2, border_color=theme.PRIMARY_SOFT)
        box.grid(row=0, column=0, padx=40, pady=30, sticky="nsew")
        inner = ctk.CTkFrame(box, fg_color="transparent")
        inner.place(relx=0.5, rely=0.5, anchor="center")
        ctk.CTkLabel(inner, text="B", width=84, height=84, corner_radius=24, fg_color=theme.PRIMARY,
                     text_color="white", font=theme.font(44, "bold")).pack()
        ctk.CTkLabel(inner, text=t("welcome.title"), font=theme.font(26, "bold"), text_color=theme.TEXT).pack(pady=(6, 4))
        ctk.CTkLabel(inner, text=t("welcome.subtitle"), font=theme.font(14), text_color=theme.MUTED,
                     wraplength=560, justify="center").pack()
        theme.accent_button(inner, text=t("welcome.button"), command=self.ask_open, width=280).pack(pady=22)
        steps = ctk.CTkFrame(inner, fg_color="transparent")
        steps.pack()
        colors = (theme.PRIMARY, theme.SUCCESS, theme.ACCENT)
        for i in range(3):
            step = theme.card(steps, fg_color=theme.SURFACE_2, border_width=0, width=210, height=130)
            step.grid(row=0, column=i, padx=8)
            step.pack_propagate(False)
            ctk.CTkLabel(step, text=str(i + 1), width=34, height=34, corner_radius=17, fg_color=colors[i],
                         text_color="white", font=theme.font(15, "bold")).pack(pady=(14, 6))
            ctk.CTkLabel(step, text=t(f"welcome.step{i + 1}"), font=theme.font(13, "bold"), text_color=theme.TEXT).pack()
            ctk.CTkLabel(step, text=t(f"welcome.step{i + 1}_text"), font=theme.font(11), text_color=theme.MUTED,
                         wraplength=180, justify="center").pack(padx=8)
        ctk.CTkLabel(inner, text=t("welcome.formats"), font=theme.font(11), text_color=theme.MUTED).pack(pady=(18, 0))
        return outer

    def _build_panel(self, panel, actions) -> None:
        # Summary tiles
        stats = theme.card(panel)
        stats.pack(fill="x", pady=(0, 12))
        theme.section_title(stats, t("panel.summary")).pack(fill="x", padx=14, pady=(12, 6))
        tiles = ctk.CTkFrame(stats, fg_color="transparent")
        tiles.pack(fill="x", padx=10, pady=(0, 6))
        tiles.columnconfigure((0, 1, 2), weight=1)
        self.stat_values = {}
        for i, (key, color) in enumerate((("pages", theme.PRIMARY), ("sheets", theme.SUCCESS), ("blanks", theme.WARNING))):
            tile = ctk.CTkFrame(tiles, fg_color=theme.SURFACE_2, corner_radius=12)
            tile.grid(row=0, column=i, padx=4, sticky="ew")
            value = ctk.CTkLabel(tile, text="–", font=theme.font(22, "bold"), text_color=color)
            value.pack(pady=(8, 0))
            ctk.CTkLabel(tile, text=t(f"stat.{key}"), font=theme.font(11), text_color=theme.MUTED).pack(pady=(0, 8))
            self.stat_values[key] = value
        self.binding_info = ctk.CTkLabel(stats, text="", font=theme.font(12), text_color=theme.MUTED, anchor="w",
                                         justify="left", wraplength=270)
        self.binding_info.pack(fill="x", padx=14, pady=(2, 12))

        # Layout
        lay = theme.card(panel)
        lay.pack(fill="x", pady=(0, 12))
        theme.section_title(lay, t("frame.layout")).pack(fill="x", padx=14, pady=(12, 6))
        self._label(lay, t("label.paper"))
        ctk.CTkSegmentedButton(
            lay, values=list(PAPER_SIZES)[:3], variable=self.paper, command=lambda v: self.layout_changed(),
            selected_color=theme.SELECTED, selected_hover_color=theme.SELECTED_HOVER, corner_radius=10,
            fg_color=theme.SURFACE_2, unselected_color=theme.SURFACE_2, unselected_hover_color=theme.PRIMARY_SOFT,
            text_color=(theme.TEXT[0], theme.TEXT[1]),
        ).pack(fill="x", padx=14)
        other = ctk.CTkOptionMenu(lay, values=list(PAPER_SIZES), variable=self.paper, height=26, corner_radius=8,
                                  command=lambda v: self.layout_changed(), fg_color=theme.SURFACE_2,
                                  button_color=theme.SURFACE_2, text_color=theme.TEXT, font=theme.font(11))
        other.pack(anchor="e", padx=14, pady=(4, 0))

        self._label(lay, t("label.binding"))
        binding_labels = [t(f"binding.{b.value}") for b in BINDINGS]
        self.binding_menu = ctk.CTkOptionMenu(
            lay, values=binding_labels, corner_radius=10, height=34,
            command=lambda v: self._set_binding(BINDINGS[binding_labels.index(v)]),
            fg_color=theme.SURFACE_2, button_color=theme.PRIMARY, button_hover_color=theme.PRIMARY_HOVER,
            text_color=theme.TEXT, font=theme.font(12),
        )
        self.binding_menu.set(binding_labels[BINDINGS.index(self.binding)])
        self.binding_menu.pack(fill="x", padx=14)

        self.margin_label = self._label(lay, "")
        ctk.CTkSlider(lay, from_=0, to=20, number_of_steps=20, variable=self.margin,
                      command=lambda v: self._sliders_changed(), progress_color=theme.PRIMARY,
                      button_color=theme.PRIMARY).pack(fill="x", padx=10)
        self.gutter_label = self._label(lay, "")
        ctk.CTkSlider(lay, from_=0, to=20, number_of_steps=20, variable=self.gutter,
                      command=lambda v: self._sliders_changed(), progress_color=theme.PRIMARY,
                      button_color=theme.PRIMARY).pack(fill="x", padx=10)
        self._update_slider_labels()
        for text, var in ((t("check.back_cover"), self.back_cover), (t("check.fold_marks"), self.fold_marks)):
            ctk.CTkSwitch(lay, text=text, variable=var, command=self.layout_changed, progress_color=theme.PRIMARY,
                          font=theme.font(12), text_color=theme.TEXT).pack(anchor="w", padx=14, pady=(10, 0))
        ctk.CTkFrame(lay, height=12, fg_color="transparent").pack()

        # Printing
        prt = theme.card(panel)
        prt.pack(fill="x", pady=(0, 12))
        theme.section_title(prt, t("frame.print")).pack(fill="x", padx=14, pady=(12, 6))
        printers = list_printers()
        if not self.printer.get():
            self.printer.set(default_printer() or (printers[0] if printers else ""))
        self._label(prt, t("label.printer"))
        ctk.CTkOptionMenu(prt, values=printers or [t("label.no_printer")], variable=self.printer, corner_radius=10,
                          fg_color=theme.SURFACE_2, button_color=theme.SURFACE_2, text_color=theme.TEXT,
                          font=theme.font(12), dynamic_resizing=False).pack(fill="x", padx=14)
        row = ctk.CTkFrame(prt, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=(10, 0))
        ctk.CTkLabel(row, text=t("label.copies"), font=theme.font(12), text_color=theme.TEXT).pack(side="left")
        theme.ghost_button(row, text="+", width=32, command=lambda: self._bump_copies(1)).pack(side="right")
        ctk.CTkEntry(row, textvariable=self.copies, width=50, justify="center", corner_radius=8).pack(side="right", padx=4)
        theme.ghost_button(row, text="−", width=32, command=lambda: self._bump_copies(-1)).pack(side="right")
        ctk.CTkSwitch(prt, text=t("switch.auto_duplex"), variable=self.auto_duplex, command=self._duplex_changed,
                      progress_color=theme.SUCCESS, font=theme.font(12), text_color=theme.TEXT).pack(anchor="w", padx=14, pady=(12, 0))
        self.duplex_hint = ctk.CTkLabel(prt, text="", font=theme.font(11), text_color=theme.MUTED, anchor="w",
                                        justify="left", wraplength=260)
        self.duplex_hint.pack(fill="x", padx=14, pady=(2, 0))
        self.reverse_switch = ctk.CTkSwitch(prt, text=t("check.reverse_backs"), variable=self.reverse_backs,
                                            progress_color=theme.PRIMARY, font=theme.font(12), text_color=theme.TEXT)
        self._duplex_changed(save=False)

        ctk.CTkFrame(prt, height=12, fg_color="transparent").pack()

        self.print_btn = theme.accent_button(actions, text=t("btn.print"), command=self.print_booklet, state="disabled")
        self.print_btn.pack(fill="x", padx=12, pady=(12, 6))
        self.save_btn = theme.ghost_button(actions, text=t("btn.save_imposed"), command=self.save_pdf, state="disabled", height=34)
        self.save_btn.pack(fill="x", padx=12)
        self.export_btn = ctk.CTkButton(actions, text=t("btn.export_pages"), command=self.export_pages, fg_color="transparent",
                                        hover_color=theme.SURFACE_2, text_color=theme.PRIMARY, font=theme.font(12),
                                        state="disabled", height=28)
        self.export_btn.pack(fill="x", padx=12, pady=(4, 10))

    def _label(self, master, text: str) -> ctk.CTkLabel:
        lbl = ctk.CTkLabel(master, text=text, font=theme.font(12), text_color=theme.TEXT, anchor="w")
        lbl.pack(fill="x", padx=14, pady=(10, 2))
        return lbl

    def _update_slider_labels(self) -> None:
        self.margin_label.configure(text=t("label.margin_value", mm=round(self.margin.get())))
        self.gutter_label.configure(text=t("label.gutter_value", mm=round(self.gutter.get())))

    def _sliders_changed(self) -> None:
        self._update_slider_labels()
        self.debounce("layout", 250, self.layout_changed)

    def _set_binding(self, binding: Binding) -> None:
        self.binding = binding
        self.layout_changed()

    def _bump_copies(self, delta: int) -> None:
        self.copies.set(str(max(1, min(999, self._copies() + delta))))

    def _duplex_changed(self, save: bool = True) -> None:
        if save:
            set_setting("auto_duplex", bool(self.auto_duplex.get()))
        if self.auto_duplex.get():
            self.duplex_hint.configure(text=t("hint.auto_duplex"))
            self.reverse_switch.pack_forget()
        else:
            self.duplex_hint.configure(text=t("hint.manual_duplex"))
            self.reverse_switch.pack(anchor="w", padx=14, pady=(6, 0), after=self.duplex_hint)

    def _bind_keys(self) -> None:
        m = self.master
        m.bind("<Control-o>", lambda e: self.ask_open())
        m.bind("<Control-p>", lambda e: self.print_booklet())
        m.bind("<Control-s>", lambda e: self.save_pdf())
        m.bind("<Control-e>", lambda e: self.export_pages())
        m.bind("<Control-z>", lambda e: self.undo())
        m.bind("<Control-y>", lambda e: self.redo())
        m.bind("<Control-Z>", lambda e: self.redo())
        m.bind("<Left>", lambda e: self._arrow(e, -1))
        m.bind("<Right>", lambda e: self._arrow(e, 1))
        m.bind("<Prior>", lambda e: self._arrow(e, -1))
        m.bind("<Next>", lambda e: self._arrow(e, 1))
        m.bind("<Delete>", lambda e: self._delete_key(e))
        m.bind("<Control-a>", lambda e: self._select_all(e))
        m.bind("<Control-d>", lambda e: self._organizer_key(e, self.plan.duplicate))

    def _typing(self, event) -> bool:
        return event.widget.winfo_class() in ("Entry", "TEntry", "Text", "Spinbox")

    def _arrow(self, event, delta: int) -> None:
        if self._typing(event) or not self.result:
            return
        if self.view == "book":
            self.book.move(delta)
        elif self.view == "sheets":
            self.sheets.move(delta)
        elif self.view == "pages":
            sel = self.organizer.selection()
            if sel:
                i = max(0, min(len(self.plan) - 1, (sel[0] if delta < 0 else sel[-1]) + delta))
                self.organizer.select([i])

    def _delete_key(self, event) -> None:
        if not self._typing(event):
            self._organizer_key(event, self.plan.delete)

    def _organizer_key(self, event, op) -> None:
        if self.view == "pages" and self.src and not self._typing(event):
            self.organizer.edit(op)

    def _select_all(self, event) -> Optional[str]:
        if self.view == "pages" and self.src and not self._typing(event):
            self.organizer.select(list(range(len(self.plan))), scroll=False)
            return "break"
        return None

    # =============================================================== views
    def _switch(self, label: str) -> None:
        labels = [t("tab.book"), t("tab.pages"), t("tab.sheets")]
        self.show_view(VIEWS[labels.index(label)])

    def show_view(self, name: str) -> None:
        if name == "welcome" or not self.src:
            self.welcome.tkraise()
            self.switcher.configure(state="disabled")
            return
        self.view = name
        self.switcher.configure(state="normal")
        self.switcher.set([t("tab.book"), t("tab.pages"), t("tab.sheets")][VIEWS.index(name)])
        frame = {"book": self.book, "pages": self.organizer, "sheets": self.sheets}[name]
        frame.tkraise()
        self.after(10, self.render_current)

    def render_current(self) -> None:
        if not self.result:
            return
        if self.view == "book":
            self.book.render()
        elif self.view == "sheets":
            self.sheets.render()
        else:
            self.organizer.render_crop()

    def open_in_editor(self, plan_index: int) -> None:
        self.show_view("pages")
        self.organizer.select([plan_index])

    def show_in_book(self, plan_index: int) -> None:
        self.show_view("book")
        self.after(20, lambda: self.book.show_position(plan_index))

    def toast(self, text: str, ms: int = 2600) -> None:
        self.toast_label.configure(text=text)
        self.toast_label.place(relx=0.5, rely=1.0, y=-24, anchor="s")
        self.toast_label.lift()
        if self._toast_job:
            self.after_cancel(self._toast_job)
        self._toast_job = self.after(ms, self.toast_label.place_forget) if ms else None

    # ============================================================= loading
    def ask_open(self) -> None:
        patterns = " ".join(f"*{e}" for e in sorted(SUPPORTED_EXTENSIONS))
        path = filedialog.askopenfilename(
            title=t("dlg.open_title"),
            filetypes=[(t("dlg.documents"), patterns), ("PDF", "*.pdf"), ("PowerPoint", "*.pptx *.ppt"), (t("dlg.all"), "*.*")],
        )
        if path:
            self.open_file(path)

    def open_file(self, path: str) -> None:
        p = Path(path)
        key = "status.loading_convert" if p.suffix.lower() != ".pdf" else "status.loading"
        self.toast(t(key, name=p.name), ms=0)
        self.master.configure(cursor="watch")

        def done(doc, error) -> None:
            self.master.configure(cursor="")
            if error:
                self.toast_label.place_forget()
                messagebox.showerror(t("dlg.open_error"), str(error))
                return
            self.src, self.src_path = doc, p
            self.plan = PagePlan.from_count(len(doc))
            self.organizer.clear_cache()
            self.book.index = self.sheets.index = 0
            self.toast(t("status.loaded", name=p.name, pages=len(doc)))
            self._document_ready([0])

        self._in_thread(lambda: load_document(p), done)

    def _document_ready(self, select: list[int]) -> None:
        self.file_label.configure(text=f"{self.src_path.name if self.src_path else ''} · {t('label.pages', n=len(self.src))}")
        for b in (self.print_btn, self.save_btn, self.export_btn):
            b.configure(state="normal")
        self.plan_changed(select)
        self.show_view(self.view if self.view in VIEWS else "book")

    # ======================================================== plan changes
    def plan_changed(self, select: Optional[list[int]] = None) -> None:
        if not self.src:
            return
        try:
            self.result = impose(self.src, self.options(), self.plan.pages)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror(t("dlg.error"), str(exc))
            return
        self.book.invalidate()
        self.organizer.refresh(select)
        self._update_stats()
        self.render_current()

    def layout_changed(self) -> None:
        set_setting("paper", self.paper.get())
        self.plan_changed(self.organizer.selection() if self.src else None)

    def _update_stats(self) -> None:
        r = self.result
        self.stat_values["pages"].configure(text=str(r.content_pages))
        self.stat_values["sheets"].configure(text=str(len(r.sheets)))
        self.stat_values["blanks"].configure(text=str(r.padding_pages))
        text = t("info.binding", binding=t(f"binding.short.{r.binding.value}"))
        edited = sum(1 for p in r.plan if p.is_adjusted)
        if edited:
            text += "\n" + t("info.edited", count=edited)
        self.binding_info.configure(text=text)

    def undo(self) -> None:
        if self.src and self.plan.undo():
            self.plan_changed(self.organizer.selection())
            self.toast(t("status.undone"), 1200)

    def redo(self) -> None:
        if self.src and self.plan.redo():
            self.plan_changed(self.organizer.selection())
            self.toast(t("status.redone"), 1200)

    def restore_original(self) -> None:
        if self.src and messagebox.askyesno(t("edit.restore"), t("dlg.restore_confirm")):
            self.plan.restore_original(len(self.src))
            self.plan_changed([0])

    # ======================================================== save / print
    def _default_name(self, suffix: str) -> str:
        return (self.src_path.stem if self.src_path else "document") + suffix

    def save_pdf(self) -> None:
        if not self.result:
            return
        path = filedialog.asksaveasfilename(defaultextension=".pdf", initialfile=self._default_name(t("file.suffix_booklet")),
                                            filetypes=[("PDF", "*.pdf")])
        if path:
            self.result.document.save(path, garbage=3, deflate=True)
            self.toast(t("status.saved", path=Path(path).name))

    def export_pages(self) -> None:
        if not self.result:
            return
        path = filedialog.asksaveasfilename(defaultextension=".pdf", initialfile=self._default_name(t("file.suffix_edited")),
                                            filetypes=[("PDF", "*.pdf")])
        if path:
            render_reading_order(self.src, self.plan.pages, self.options()).save(path, garbage=3, deflate=True)
            self.toast(t("status.saved", path=Path(path).name))

    def print_booklet(self) -> None:
        if not self.result:
            return
        printer = self.printer.get()
        if printer == t("label.no_printer"):
            printer = ""
        base = PrintOptions(printer=printer or None, paper=self.paper.get(), title=self._default_name(t("file.suffix_booklet")))
        copies = self._copies()
        try:
            if self.auto_duplex.get():
                base.copies = copies
                print_document(self.result.document, base)
                self.toast(t("status.sent"))
                return
            full = fitz.open()
            for _ in range(copies):
                full.insert_pdf(self.result.document)
            fronts, backs = split_sides(full, reverse_backs=self.reverse_backs.get())
            base.duplex = False
            print_document(fronts, base)
            messagebox.showinfo(t("dlg.manual_title"), t("dlg.manual_body"))
            print_document(backs, base)
            self.toast(t("status.backs_sent"))
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror(t("dlg.print_error"), str(exc))

    # ================================================ language / appearance
    def change_language(self, code: str) -> None:
        set_setting("language", code)
        set_language(code)
        state = self._export_state()
        master = self.master
        self.destroy()
        App(master, state=state)

    def change_appearance(self, mode: str) -> None:
        set_setting("appearance", mode)
        ctk.set_appearance_mode(mode)
        self.book.invalidate()
        self.after(50, self.render_current)

    # ============================================================= updates
    def _in_thread(self, work: Callable[[], object], done: Callable[[object, Optional[Exception]], None]) -> None:
        box: dict = {}

        def target() -> None:
            try:
                box["value"] = work()
            except Exception as exc:  # noqa: BLE001
                box["error"] = exc

        thread = threading.Thread(target=target, daemon=True)
        thread.start()

        def poll() -> None:
            if self._progress_text:
                self.toast(self._progress_text, ms=0)
            if thread.is_alive():
                self.after(150, poll)
            else:
                self._progress_text = None
                done(box.get("value"), box.get("error"))

        poll()

    def check_updates(self, silent: bool) -> None:
        def done(release, error) -> None:
            if error:
                if not silent:
                    messagebox.showerror(t("dlg.update_title"), str(error))
                return
            if release is None:
                if not silent:
                    messagebox.showinfo(t("dlg.update_title"), t("dlg.up_to_date", version=__version__))
                return
            notes = release.notes.strip()
            if len(notes) > 800:
                notes = notes[:800] + "…"
            if not updater.is_frozen_windows():
                messagebox.showinfo(t("dlg.update_available"), t("dlg.update_link", version=release.version, url=release.html_url))
                return
            if messagebox.askyesno(t("dlg.update_available"),
                                   t("dlg.update_ask", version=release.version, current=__version__, notes=notes)):
                self.install_update(release)

        self._in_thread(updater.check_for_update, done)

    def install_update(self, release) -> None:
        dest = Path(tempfile.gettempdir()) / f"BookletPrinter-{release.version}.exe"

        def progress(done: int, total: int) -> None:
            pct = f" {done * 100 // total} %" if total else ""
            self._progress_text = t("status.downloading", pct=pct)

        def finished(_value, error) -> None:
            self.toast_label.place_forget()
            if error:
                messagebox.showerror(t("dlg.update_title"), str(error))
                return
            try:
                updater.install_and_restart(dest)
            except Exception as exc:  # noqa: BLE001
                messagebox.showerror(t("dlg.update_title"), str(exc))
                return
            self.master.destroy()

        self._in_thread(lambda: updater.download(release, dest, progress), finished)


def run(initial: Optional[str] = None) -> None:
    if sys.platform.startswith("win"):
        try:
            import ctypes

            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:  # noqa: BLE001
            pass
    theme.setup()
    ctk.set_appearance_mode(get_setting("appearance", "system"))
    root = ctk.CTk(fg_color=theme.BG)
    root.geometry("1440x900")
    root.minsize(1100, 700)
    App(root, initial)
    root.mainloop()
