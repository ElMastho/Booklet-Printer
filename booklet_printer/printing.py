"""Send an imposed booklet to a printer.

* Windows: printing through GDI (pywin32) so that duplex "flip on short edge",
  orientation and paper size can be forced on the job.
* macOS / Linux: CUPS ``lp`` with ``-o sides=two-sided-short-edge``.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pymupdf as fitz

IS_WINDOWS = sys.platform.startswith("win")


class PrintError(RuntimeError):
    pass


@dataclass
class PrintOptions:
    printer: Optional[str] = None  # None = default printer
    copies: int = 1
    duplex: bool = True  # False = one-sided (used for the manual duplex passes)
    paper: str = "A4"
    title: str = "Booklet"
    dpi: int = 300  # Windows only: rasterisation resolution


# ---------------------------------------------------------------- discovery

def list_printers() -> list[str]:
    if IS_WINDOWS:
        try:
            import win32print

            flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
            return [p[2] for p in win32print.EnumPrinters(flags)]
        except Exception:
            return []
    if not shutil.which("lpstat"):
        return []
    out = subprocess.run(["lpstat", "-e"], capture_output=True, text=True).stdout
    return [line.strip() for line in out.splitlines() if line.strip()]


def default_printer() -> Optional[str]:
    if IS_WINDOWS:
        try:
            import win32print

            return win32print.GetDefaultPrinter()
        except Exception:
            return None
    if not shutil.which("lpstat"):
        return None
    out = subprocess.run(["lpstat", "-d"], capture_output=True, text=True).stdout
    if ":" in out:
        name = out.split(":", 1)[1].strip()
        return name or None
    return None


# ------------------------------------------------------------------- print

def print_document(doc: fitz.Document, opts: PrintOptions) -> None:
    if len(doc) == 0:
        raise PrintError("Rien à imprimer.")
    if IS_WINDOWS:
        _print_windows(doc, opts)
    else:
        _print_cups(doc, opts)


def _print_cups(doc: fitz.Document, opts: PrintOptions) -> None:
    lp = shutil.which("lp")
    if not lp:
        raise PrintError("La commande 'lp' (CUPS) est introuvable.")
    media = {"A4": "A4", "A3": "A3", "Letter": "Letter", "Legal": "Legal", "Tabloid": "Tabloid"}[opts.paper]
    fd, tmp = tempfile.mkstemp(suffix=".pdf", prefix="booklet-")
    os.close(fd)
    try:
        doc.save(tmp)
        cmd = [lp, "-t", opts.title, "-n", str(max(1, opts.copies)), "-o", f"media={media}"]
        cmd += ["-o", "sides=two-sided-short-edge" if opts.duplex else "sides=one-sided"]
        if opts.copies > 1:
            cmd += ["-o", "collate=true"]
        if opts.printer:
            cmd += ["-d", opts.printer]
        cmd.append(tmp)
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise PrintError(proc.stderr.strip() or "Échec de l'impression.")
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


# Windows constants (wingdi.h)
_DMPAPER = {"A4": 9, "A3": 8, "Letter": 1, "Legal": 5, "Tabloid": 3}
_DM_ORIENTATION, _DM_PAPERSIZE, _DM_COPIES, _DM_COLLATE, _DM_DUPLEX = 0x1, 0x2, 0x100, 0x8000, 0x1000
_DMORIENT_PORTRAIT, _DMORIENT_LANDSCAPE = 1, 2
_DMDUP_SIMPLEX, _DMDUP_HORIZONTAL = 1, 3  # HORIZONTAL = flip on short edge
_DM_IN_BUFFER, _DM_OUT_BUFFER = 8, 2
_HORZRES, _VERTRES = 8, 10
_PHYSICALWIDTH, _PHYSICALHEIGHT, _PHYSICALOFFSETX, _PHYSICALOFFSETY = 110, 111, 112, 113
_LOGPIXELSX = 88


def _print_windows(doc: fitz.Document, opts: PrintOptions) -> None:
    try:
        import win32gui
        import win32print
        import win32ui
        from PIL import Image, ImageWin
    except ImportError as exc:  # pragma: no cover - windows only
        raise PrintError("pywin32 et Pillow sont nécessaires pour imprimer sous Windows.") from exc

    name = opts.printer or win32print.GetDefaultPrinter()
    first = doc[0].rect
    landscape = first.width > first.height

    handle = win32print.OpenPrinter(name)
    try:
        devmode = win32print.GetPrinter(handle, 2)["pDevMode"]
        devmode.Orientation = _DMORIENT_LANDSCAPE if landscape else _DMORIENT_PORTRAIT
        devmode.PaperSize = _DMPAPER[opts.paper]
        devmode.Duplex = _DMDUP_HORIZONTAL if opts.duplex else _DMDUP_SIMPLEX
        devmode.Copies = max(1, opts.copies)
        devmode.Collate = 1
        devmode.Fields |= _DM_ORIENTATION | _DM_PAPERSIZE | _DM_DUPLEX | _DM_COPIES | _DM_COLLATE
        win32print.DocumentProperties(0, handle, name, devmode, devmode, _DM_IN_BUFFER | _DM_OUT_BUFFER)
    finally:
        win32print.ClosePrinter(handle)

    hdc = win32gui.CreateDC("WINSPOOL", name, devmode)
    dc = win32ui.CreateDCFromHandle(hdc)
    try:
        printer_dpi = dc.GetDeviceCaps(_LOGPIXELSX)
        phys_w, phys_h = dc.GetDeviceCaps(_PHYSICALWIDTH), dc.GetDeviceCaps(_PHYSICALHEIGHT)
        off_x, off_y = dc.GetDeviceCaps(_PHYSICALOFFSETX), dc.GetDeviceCaps(_PHYSICALOFFSETY)
        dpi = min(opts.dpi, printer_dpi)
        dc.StartDoc(opts.title)
        for page in doc:
            dc.StartPage()
            pix = page.get_pixmap(dpi=dpi, alpha=False)
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            # Map the whole PDF page onto the physical sheet (true scale),
            # the origin of the device context being the printable area corner.
            ImageWin.Dib(img).draw(dc.GetHandleOutput(), (-off_x, -off_y, phys_w - off_x, phys_h - off_y))
            dc.EndPage()
        dc.EndDoc()
    except Exception as exc:  # pragma: no cover - windows only
        try:
            dc.AbortDoc()
        except Exception:
            pass
        raise PrintError(f"Échec de l'impression : {exc}") from exc
    finally:
        dc.DeleteDC()


def open_with_system_viewer(path: str | os.PathLike) -> None:
    path = str(Path(path))
    if IS_WINDOWS:
        os.startfile(path)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])
