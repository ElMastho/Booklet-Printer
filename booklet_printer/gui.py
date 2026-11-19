"""Tkinter interface: open a PDF/PPTX, preview the booklet, save or print it."""

from __future__ import annotations

import base64
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Optional

import pymupdf as fitz

from . import __version__
from .convert import SUPPORTED_EXTENSIONS, load_document
from .imposition import (
    PAPER_SIZES,
    Binding,
    ImposeOptions,
    ImposeResult,
    Side,
    impose,
    page_sequence,
    sheet_geometry,
    split_sides,
)
from .printing import PrintOptions, default_printer, list_printers, print_document
from . import updater

BINDING_LABELS = {
    "Automatique": Binding.AUTO,
    "À gauche (classique)": Binding.LEFT,
    "À droite (lecture droite → gauche)": Binding.RIGHT,
    "En haut (calendrier, idéal diapos)": Binding.TOP,
}
BINDING_NAMES = {Binding.LEFT: "à gauche", Binding.RIGHT: "à droite", Binding.TOP: "en haut"}

HELP_TEXT = (
    "Impression : recto-verso, retournement sur le BORD COURT, échelle 100 %.\n"
    "Pliage : imbriquez les feuilles, la feuille 1 à l'extérieur (couverture), "
    "pliez l'ensemble en deux et agrafez au pli."
)


class App(ttk.Frame):
    def __init__(self, master: tk.Tk, initial: Optional[str] = None):
        super().__init__(master, padding=8)
        self.master = master
        self.src: Optional[fitz.Document] = None
        self.src_path: Optional[Path] = None
        self.result: Optional[ImposeResult] = None
        self.index = 0  # current sheet (imposed view) or spread (reading view)
        self._images: list[tk.PhotoImage] = []
        self._resize_job: Optional[str] = None

        master.title(f"Booklet Printer {__version__}")
        master.geometry("1200x780")
        master.minsize(900, 600)
        self.grid(sticky="nsew")
        master.columnconfigure(0, weight=1)
        master.rowconfigure(0, weight=1)

        self._build()
        self._build_menu()
        self._bind_keys()
        if updater.is_frozen_windows() and updater.load_config().get("auto_update", True):
            self.after(1500, lambda: self.check_updates(silent=True))
        if initial:
            self.after(100, lambda: self.open_file(initial))

    # ------------------------------------------------------------------ UI
    def _build(self) -> None:
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        side = ttk.Frame(self)
        side.grid(row=0, column=0, sticky="ns", padx=(0, 8))

        ttk.Button(side, text="Ouvrir un PDF / PPTX…", command=self.ask_open).pack(fill="x")
        self.file_label = ttk.Label(side, text="Aucun fichier", wraplength=260, foreground="#555")
        self.file_label.pack(fill="x", pady=(4, 10))

        opts = ttk.LabelFrame(side, text="Mise en page", padding=8)
        opts.pack(fill="x")
        self.paper = tk.StringVar(value="A4")
        self.binding = tk.StringVar(value="Automatique")
        self.margin = tk.DoubleVar(value=5.0)
        self.gutter = tk.DoubleVar(value=0.0)
        self.back_cover = tk.BooleanVar(value=False)
        self.fold_marks = tk.BooleanVar(value=False)

        ttk.Label(opts, text="Papier").grid(row=0, column=0, sticky="w")
        ttk.Combobox(opts, textvariable=self.paper, values=list(PAPER_SIZES), state="readonly", width=24).grid(
            row=0, column=1, sticky="ew", pady=2
        )
        ttk.Label(opts, text="Reliure").grid(row=1, column=0, sticky="w")
        ttk.Combobox(opts, textvariable=self.binding, values=list(BINDING_LABELS), state="readonly", width=24).grid(
            row=1, column=1, sticky="ew", pady=2
        )
        ttk.Label(opts, text="Marge (mm)").grid(row=2, column=0, sticky="w")
        ttk.Spinbox(opts, textvariable=self.margin, from_=0, to=30, increment=1, width=6).grid(
            row=2, column=1, sticky="w", pady=2
        )
        ttk.Label(opts, text="Gouttière (mm)").grid(row=3, column=0, sticky="w")
        ttk.Spinbox(opts, textvariable=self.gutter, from_=0, to=30, increment=1, width=6).grid(
            row=3, column=1, sticky="w", pady=2
        )
        ttk.Checkbutton(opts, text="Dernière page en 4ᵉ de couverture", variable=self.back_cover).grid(
            row=4, column=0, columnspan=2, sticky="w", pady=(6, 0)
        )
        ttk.Checkbutton(opts, text="Traits de pliage", variable=self.fold_marks).grid(
            row=5, column=0, columnspan=2, sticky="w"
        )
        for var in (self.paper, self.binding, self.back_cover, self.fold_marks, self.margin, self.gutter):
            var.trace_add("write", lambda *_: self._schedule_rebuild())

        self.info = ttk.Label(side, text="", wraplength=260, justify="left")
        self.info.pack(fill="x", pady=10)

        prt = ttk.LabelFrame(side, text="Impression", padding=8)
        prt.pack(fill="x")
        printers = list_printers()
        self.printer = tk.StringVar(value=default_printer() or (printers[0] if printers else ""))
        self.copies = tk.IntVar(value=1)
        self.duplex_mode = tk.StringVar(value="auto")
        self.reverse_versos = tk.BooleanVar(value=False)
        ttk.Label(prt, text="Imprimante").grid(row=0, column=0, sticky="w")
        ttk.Combobox(prt, textvariable=self.printer, values=printers, width=24).grid(row=0, column=1, sticky="ew", pady=2)
        ttk.Label(prt, text="Exemplaires").grid(row=1, column=0, sticky="w")
        ttk.Spinbox(prt, textvariable=self.copies, from_=1, to=999, width=6).grid(row=1, column=1, sticky="w", pady=2)
        ttk.Radiobutton(prt, text="Recto-verso automatique", value="auto", variable=self.duplex_mode).grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(6, 0)
        )
        ttk.Radiobutton(prt, text="Recto-verso manuel (2 passages)", value="manual", variable=self.duplex_mode).grid(
            row=3, column=0, columnspan=2, sticky="w"
        )
        ttk.Checkbutton(prt, text="Inverser l'ordre des versos", variable=self.reverse_versos).grid(
            row=4, column=0, columnspan=2, sticky="w", padx=(18, 0)
        )

        self.print_btn = ttk.Button(side, text="Imprimer", command=self.print_booklet, state="disabled")
        self.print_btn.pack(fill="x", pady=(10, 2))
        self.save_btn = ttk.Button(side, text="Enregistrer le PDF imposé…", command=self.save_pdf, state="disabled")
        self.save_btn.pack(fill="x")
        ttk.Label(side, text=HELP_TEXT, wraplength=260, foreground="#555", justify="left").pack(fill="x", pady=10)

        # Preview
        right = ttk.Frame(self)
        right.grid(row=0, column=1, sticky="nsew")
        right.rowconfigure(1, weight=1)
        right.columnconfigure(0, weight=1)

        bar = ttk.Frame(right)
        bar.grid(row=0, column=0, sticky="ew")
        self.view = tk.StringVar(value="sheets")
        ttk.Radiobutton(bar, text="Feuilles à imprimer", value="sheets", variable=self.view, command=self._view_changed).pack(side="left")
        ttk.Radiobutton(bar, text="Livret plié (lecture)", value="reading", variable=self.view, command=self._view_changed).pack(side="left", padx=8)
        ttk.Button(bar, text="▶", width=3, command=lambda: self.go(1)).pack(side="right")
        self.nav_label = ttk.Label(bar, text="", width=26, anchor="center")
        self.nav_label.pack(side="right")
        ttk.Button(bar, text="◀", width=3, command=lambda: self.go(-1)).pack(side="right")

        self.canvas = tk.Canvas(right, background="#8a8f98", highlightthickness=0)
        self.canvas.grid(row=1, column=0, sticky="nsew", pady=(6, 0))
        self.canvas.bind("<Configure>", lambda e: self._schedule_render())
        self.status = ttk.Label(right, text="Ouvrez un fichier pour commencer.", anchor="w")
        self.status.grid(row=2, column=0, sticky="ew", pady=(4, 0))

    def _build_menu(self) -> None:
        menubar = tk.Menu(self.master)
        file_menu = tk.Menu(menubar, tearoff=False)
        file_menu.add_command(label="Ouvrir…", accelerator="Ctrl+O", command=self.ask_open)
        file_menu.add_command(label="Enregistrer le PDF imposé…", accelerator="Ctrl+S", command=self.save_pdf)
        file_menu.add_command(label="Imprimer", accelerator="Ctrl+P", command=self.print_booklet)
        file_menu.add_separator()
        file_menu.add_command(label="Quitter", command=self.master.destroy)
        menubar.add_cascade(label="Fichier", menu=file_menu)
        help_menu = tk.Menu(menubar, tearoff=False)
        self.auto_update = tk.BooleanVar(value=updater.load_config().get("auto_update", True))
        help_menu.add_command(label="Rechercher des mises à jour", command=lambda: self.check_updates(silent=False))
        help_menu.add_checkbutton(
            label="Vérifier au démarrage", variable=self.auto_update, command=self._toggle_auto_update
        )
        help_menu.add_separator()
        help_menu.add_command(label="À propos", command=self.about)
        menubar.add_cascade(label="Aide", menu=help_menu)
        self.master.config(menu=menubar)

    def _toggle_auto_update(self) -> None:
        cfg = updater.load_config()
        cfg["auto_update"] = bool(self.auto_update.get())
        updater.save_config(cfg)

    def about(self) -> None:
        messagebox.showinfo(
            "À propos",
            f"Booklet Printer {__version__}\n\nImpose un PDF ou un PPTX en livret "
            f"(cahier piqué) et l'imprime en recto-verso.\n\nhttps://github.com/{updater.REPO}",
        )

    # ------------------------------------------------------------- updates
    def _in_thread(self, work, done) -> None:
        box: dict = {}

        def target() -> None:
            try:
                box["value"] = work()
            except Exception as exc:  # noqa: BLE001
                box["error"] = exc

        thread = threading.Thread(target=target, daemon=True)
        thread.start()

        def poll() -> None:
            text = getattr(self, "_progress_text", None)
            if text:
                self.status.config(text=text)
            if thread.is_alive():
                self.after(200, poll)
            else:
                self._progress_text = None
                done(box.get("value"), box.get("error"))

        poll()

    def check_updates(self, silent: bool) -> None:
        def done(release, error) -> None:
            if error:
                if not silent:
                    messagebox.showerror("Mise à jour", str(error))
                return
            if release is None:
                if not silent:
                    messagebox.showinfo("Mise à jour", f"Vous utilisez la dernière version ({__version__}).")
                return
            notes = release.notes.strip()
            if len(notes) > 800:
                notes = notes[:800] + "…"
            if not updater.is_frozen_windows():
                messagebox.showinfo(
                    "Mise à jour disponible",
                    f"La version {release.version} est disponible :\n{release.html_url}",
                )
                return
            if messagebox.askyesno(
                "Mise à jour disponible",
                f"La version {release.version} est disponible (vous avez {__version__}).\n\n{notes}\n\n"
                "Installer maintenant ? L'application va redémarrer.",
            ):
                self.install_update(release)

        self.status.config(text="Recherche de mises à jour…")
        self._in_thread(updater.check_for_update, lambda r, e: (self.status.config(text=""), done(r, e)))

    def install_update(self, release) -> None:
        import tempfile

        dest = Path(tempfile.gettempdir()) / f"BookletPrinter-{release.version}.exe"

        def progress(done: int, total: int) -> None:
            pct = f" {done * 100 // total} %" if total else ""
            self._progress_text = f"Téléchargement de la mise à jour…{pct}"

        def finished(_value, error) -> None:
            if error:
                messagebox.showerror("Mise à jour", str(error))
                self.status.config(text="Échec de la mise à jour.")
                return
            try:
                updater.install_and_restart(dest)
            except Exception as exc:  # noqa: BLE001
                messagebox.showerror("Mise à jour", str(exc))
                return
            self.master.destroy()

        self._in_thread(lambda: updater.download(release, dest, progress), finished)

    def _bind_keys(self) -> None:
        self.master.bind("<Left>", lambda e: self.go(-1))
        self.master.bind("<Right>", lambda e: self.go(1))
        self.master.bind("<Prior>", lambda e: self.go(-1))
        self.master.bind("<Next>", lambda e: self.go(1))
        self.master.bind("<Control-o>", lambda e: self.ask_open())
        self.master.bind("<Control-p>", lambda e: self.print_booklet())
        self.master.bind("<Control-s>", lambda e: self.save_pdf())

    # ------------------------------------------------------------- loading
    def ask_open(self) -> None:
        patterns = " ".join(f"*{e}" for e in sorted(SUPPORTED_EXTENSIONS))
        path = filedialog.askopenfilename(
            title="Choisir un document",
            filetypes=[("Documents", patterns), ("PDF", "*.pdf"), ("PowerPoint", "*.pptx *.ppt"), ("Tous", "*.*")],
        )
        if path:
            self.open_file(path)

    def open_file(self, path: str) -> None:
        p = Path(path)
        self.status.config(text=f"Chargement de {p.name}…" + (" (conversion LibreOffice)" if p.suffix.lower() != ".pdf" else ""))
        self.master.config(cursor="watch")
        box: dict = {}

        def work() -> None:
            try:
                box["doc"] = load_document(p)
            except Exception as exc:  # noqa: BLE001
                box["error"] = exc

        thread = threading.Thread(target=work, daemon=True)
        thread.start()

        def poll() -> None:
            if thread.is_alive():
                self.after(150, poll)
                return
            self.master.config(cursor="")
            if "error" in box:
                self.status.config(text="Erreur de chargement.")
                messagebox.showerror("Impossible d'ouvrir le fichier", str(box["error"]))
                return
            self.src, self.src_path, self.index = box["doc"], p, 0
            self.file_label.config(text=p.name, foreground="#000")
            self.rebuild()

        poll()

    # ---------------------------------------------------------- imposition
    def options(self) -> ImposeOptions:
        def num(var: tk.Variable, default: float) -> float:
            try:
                return max(0.0, float(var.get()))
            except (tk.TclError, ValueError):
                return default

        return ImposeOptions(
            paper=self.paper.get(),
            binding=BINDING_LABELS[self.binding.get()],
            margin_mm=num(self.margin, 5.0),
            gutter_mm=num(self.gutter, 0.0),
            keep_back_cover=self.back_cover.get(),
            fold_marks=self.fold_marks.get(),
        )

    def _schedule_rebuild(self) -> None:
        if self._resize_job:
            self.after_cancel(self._resize_job)
        self._resize_job = self.after(250, self.rebuild)

    def rebuild(self) -> None:
        self._resize_job = None
        if not self.src:
            return
        try:
            self.result = impose(self.src, self.options())
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Erreur", str(exc))
            return
        r = self.result
        nsheets = len(r.sheets)
        self.info.config(
            text=(
                f"{r.source_pages} pages → {nsheets} feuille{'s' if nsheets > 1 else ''} "
                f"({r.source_pages + r.blank_pages} pages"
                + (f", dont {r.blank_pages} blanche{'s' if r.blank_pages > 1 else ''}" if r.blank_pages else "")
                + f")\nReliure {BINDING_NAMES[r.binding]}."
            )
        )
        self.print_btn.config(state="normal")
        self.save_btn.config(state="normal")
        self.index = min(self.index, self._count() - 1)
        self.render()

    # ------------------------------------------------------------- preview
    def _count(self) -> int:
        if not self.result:
            return 0
        if self.view.get() == "sheets":
            return len(self.result.sheets)
        return len(self.result.sheets) * 2 + 1  # cover, inner spreads, back cover

    def _view_changed(self) -> None:
        self.index = 0
        self.render()

    def go(self, delta: int) -> None:
        if not self.result:
            return
        self.index = max(0, min(self._count() - 1, self.index + delta))
        self.render()

    def _schedule_render(self) -> None:
        if self._resize_job:
            self.after_cancel(self._resize_job)
        self._resize_job = self.after(120, self.rebuild if self.src and not self.result else self.render)

    def _page_image(self, page: fitz.Page, max_w: float, max_h: float) -> tuple[tk.PhotoImage, float]:
        zoom = min(max_w / page.rect.width, max_h / page.rect.height)
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        img = tk.PhotoImage(data=base64.b64encode(pix.tobytes("png")))
        return img, zoom

    def _draw_page(self, page: fitz.Page, x: float, y: float, w: float, h: float, side: Side, caption: str) -> None:
        """Draw one imposed side centred in the box (x, y, w, h) with page labels."""
        img, zoom = self._page_image(page, w, h - 22)
        self._images.append(img)
        px = x + (w - img.width()) / 2
        py = y + 22 + (h - 22 - img.height()) / 2
        c = self.canvas
        c.create_text(x + w / 2, y + 10, text=caption, fill="white", font=("TkDefaultFont", 11, "bold"))
        c.create_rectangle(px + 4, py + 4, px + img.width() + 4, py + img.height() + 4, fill="#555", outline="")
        c.create_image(px, py, image=img, anchor="nw")
        _, first, second = sheet_geometry(self.options(), self.result.binding)
        seq = page_sequence(self.result.source_pages, self.options().keep_back_cover)
        for slot, area in ((side.first, first), (side.second, second)):
            ax0, ay0 = px + area.x0 * zoom, py + area.y0 * zoom
            ax1, ay1 = px + area.x1 * zoom, py + area.y1 * zoom
            c.create_rectangle(ax0, ay0, ax1, ay1, outline="#4a90d9", dash=(3, 3))
            label = "vide" if seq[slot] is None else f"p. {seq[slot] + 1}"
            if seq[slot] is None:
                c.create_text((ax0 + ax1) / 2, (ay0 + ay1) / 2, text="page blanche", fill="#999")
            tx, ty = ax0 + 6, ay0 + 6
            item = c.create_text(tx, ty, text=label, anchor="nw", fill="white", font=("TkDefaultFont", 9, "bold"))
            bb = c.bbox(item)
            bg = c.create_rectangle(bb[0] - 3, bb[1] - 1, bb[2] + 3, bb[3] + 1, fill="#4a90d9", outline="")
            c.tag_lower(bg, item)

    def render(self) -> None:
        self._resize_job = None
        c = self.canvas
        c.delete("all")
        self._images.clear()
        if not self.result:
            return
        W, H = max(c.winfo_width(), 200), max(c.winfo_height(), 200)
        pad = 16
        doc = self.result.document
        if self.view.get() == "sheets":
            sheet = self.result.sheets[self.index]
            rec, ver = doc[2 * self.index], doc[2 * self.index + 1]
            landscape = rec.rect.width > rec.rect.height
            if landscape:  # stack recto above verso
                bh = (H - 3 * pad) / 2
                self._draw_page(rec, pad, pad, W - 2 * pad, bh, sheet.recto, "RECTO")
                self._draw_page(ver, pad, 2 * pad + bh, W - 2 * pad, bh, sheet.verso, "VERSO (au dos, bord court)")
            else:
                bw = (W - 3 * pad) / 2
                self._draw_page(rec, pad, pad, bw, H - 2 * pad, sheet.recto, "RECTO")
                self._draw_page(ver, 2 * pad + bw, pad, bw, H - 2 * pad, sheet.verso, "VERSO (au dos, bord court)")
            self.nav_label.config(text=f"Feuille {self.index + 1} / {len(self.result.sheets)}")
            self.status.config(text="Les numéros bleus indiquent la page du document source placée à cet endroit.")
        else:
            self._render_reading(W, H, pad)

    def _render_reading(self, W: int, H: int, pad: int) -> None:
        """Simulate the folded booklet: cover, spreads, back cover."""
        r = self.result
        seq = page_sequence(r.source_pages, self.options().keep_back_cover)
        n = len(seq)
        i = self.index
        if i == 0:
            pair, caption = (None, 0), "Couverture"
        elif i == self._count() - 1:
            pair, caption = (n - 1, None), "4ᵉ de couverture"
        else:
            pair, caption = (2 * i - 1, 2 * i), f"Double page {i} / {self._count() - 2}"
        if r.binding == Binding.RIGHT:
            pair = (pair[1], pair[0])
        _, first, second = sheet_geometry(self.options(), r.binding)
        tmp = fitz.open()
        page = tmp.new_page(width=r.document[0].rect.width, height=r.document[0].rect.height)
        for pos, area in zip(pair, (first, second)):
            if pos is None:
                continue
            if seq[pos] is None:
                page.draw_rect(area, color=(0.8, 0.8, 0.8), dashes="[3] 0")
            else:
                page.show_pdf_page(area, self.src, seq[pos])
        pr = page.rect
        if r.binding == Binding.TOP:
            page.draw_line((0, pr.height / 2), (pr.width, pr.height / 2), color=(0.6, 0.6, 0.6), dashes="[4] 0")
        else:
            page.draw_line((pr.width / 2, 0), (pr.width / 2, pr.height), color=(0.6, 0.6, 0.6), dashes="[4] 0")
        self._images.clear()
        img, _ = self._page_image(page, W - 2 * pad, H - 2 * pad - 22)
        self._images.append(img)
        self.canvas.create_text(W / 2, pad, text=caption, fill="white", font=("TkDefaultFont", 11, "bold"))
        self.canvas.create_image((W - img.width()) / 2, pad + 22, image=img, anchor="nw")
        self.nav_label.config(text=caption)
        self.status.config(text="Aperçu du livret une fois plié, tel qu'on le lit.")

    # ------------------------------------------------------ save and print
    def _default_name(self) -> str:
        return (self.src_path.stem if self.src_path else "document") + "-livret.pdf"

    def save_pdf(self) -> None:
        if not self.result:
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".pdf", initialfile=self._default_name(), filetypes=[("PDF", "*.pdf")]
        )
        if not path:
            return
        self.result.document.save(path, garbage=3, deflate=True)
        self.status.config(text=f"Enregistré : {path}")

    def print_booklet(self) -> None:
        if not self.result:
            return
        opts = self.options()
        copies = max(1, int(self.copies.get() or 1))
        base = PrintOptions(printer=self.printer.get() or None, paper=opts.paper, title=self._default_name())
        try:
            if self.duplex_mode.get() == "auto":
                base.copies = copies
                print_document(self.result.document, base)
                self.status.config(text="Envoyé à l'imprimante (recto-verso, bord court).")
                return
            # Manual duplex: repeat the document for each copy, then two passes.
            full = fitz.open()
            for _ in range(copies):
                full.insert_pdf(self.result.document)
            rectos, versos = split_sides(full, reverse_versos=self.reverse_versos.get())
            base.duplex = False
            print_document(rectos, base)
            messagebox.showinfo(
                "Recto-verso manuel",
                "Les rectos sont en cours d'impression.\n\n"
                "Quand c'est terminé, reprenez la pile SANS changer l'ordre des feuilles, "
                "retournez-la en la faisant pivoter sur le BORD COURT, et remettez-la dans le bac.\n\n"
                "Cliquez sur OK pour imprimer les versos.\n\n"
                "Astuce : si les versos sortent dans le mauvais ordre, cochez "
                "« Inverser l'ordre des versos » la prochaine fois.",
            )
            print_document(versos, base)
            self.status.config(text="Versos envoyés à l'imprimante.")
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Impression impossible", str(exc))


def run(initial: Optional[str] = None) -> None:
    root = tk.Tk()
    try:
        ttk.Style(root).theme_use("clam" if root.tk.call("tk", "windowingsystem") == "x11" else ttk.Style(root).theme_use())
    except tk.TclError:
        pass
    App(root, initial)
    root.mainloop()
