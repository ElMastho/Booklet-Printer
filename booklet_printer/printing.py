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

from .i18n import t

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
    output_file: Optional[str] = None  # Windows only: print to this file (tests, "Print to PDF")


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

def print_document(doc: fitz.Document, opts: PrintOptions) -> Optional[str]:
    """Print ``doc``. Returns a warning to show the user, or None."""
    if len(doc) == 0:
        raise PrintError(t("prn.nothing"))
    if IS_WINDOWS:
        return _print_windows(doc, opts)
    _print_cups(doc, opts)
    return None


def _print_cups(doc: fitz.Document, opts: PrintOptions) -> None:
    lp = shutil.which("lp")
    if not lp:
        raise PrintError(t("prn.no_lp"))
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
            raise PrintError(proc.stderr.strip() or t("prn.failed", error=""))
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
_LOGPIXELSX = 88
_PHYSICALWIDTH, _PHYSICALHEIGHT, _PHYSICALOFFSETX, _PHYSICALOFFSETY = 110, 111, 112, 113
_HALFTONE, _DIB_RGB_COLORS, _SRCCOPY = 4, 0, 0x00CC0020


def _gdi():  # pragma: no cover - windows only
    """gdi32 entry points through ctypes, with explicit signatures and last-error capture."""
    import ctypes
    from ctypes import wintypes

    gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)

    class DOCINFOW(ctypes.Structure):
        _fields_ = [
            ("cbSize", ctypes.c_int),
            ("lpszDocName", wintypes.LPCWSTR),
            ("lpszOutput", wintypes.LPCWSTR),
            ("lpszDatatype", wintypes.LPCWSTR),
            ("fwType", wintypes.DWORD),
        ]

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [
            ("biSize", wintypes.DWORD),
            ("biWidth", wintypes.LONG),
            ("biHeight", wintypes.LONG),
            ("biPlanes", wintypes.WORD),
            ("biBitCount", wintypes.WORD),
            ("biCompression", wintypes.DWORD),
            ("biSizeImage", wintypes.DWORD),
            ("biXPelsPerMeter", wintypes.LONG),
            ("biYPelsPerMeter", wintypes.LONG),
            ("biClrUsed", wintypes.DWORD),
            ("biClrImportant", wintypes.DWORD),
        ]

    HDC = wintypes.HDC
    gdi32.StartDocW.argtypes = [HDC, ctypes.POINTER(DOCINFOW)]
    gdi32.StartDocW.restype = ctypes.c_int
    for fn in ("StartPage", "EndPage", "EndDoc", "AbortDoc"):
        getattr(gdi32, fn).argtypes = [HDC]
        getattr(gdi32, fn).restype = ctypes.c_int
    gdi32.GetDeviceCaps.argtypes = [HDC, ctypes.c_int]
    gdi32.GetDeviceCaps.restype = ctypes.c_int
    gdi32.SetStretchBltMode.argtypes = [HDC, ctypes.c_int]
    gdi32.SetBrushOrgEx.argtypes = [HDC, ctypes.c_int, ctypes.c_int, ctypes.c_void_p]
    gdi32.StretchDIBits.argtypes = [HDC] + [ctypes.c_int] * 8 + [ctypes.c_void_p, ctypes.c_void_p,
                                                                ctypes.c_uint, wintypes.DWORD]
    gdi32.StretchDIBits.restype = ctypes.c_int
    gdi32.DeleteDC.argtypes = [HDC]
    return ctypes, gdi32, DOCINFOW, BITMAPINFOHEADER


def _win_error(ctypes, what: str) -> str:  # pragma: no cover - windows only
    code = ctypes.get_last_error()
    return f"{what} (Windows error {code}: {ctypes.FormatError(code).strip()})" if code else what


def _devmodes(name: str, landscape: bool, opts: PrintOptions) -> list:  # pragma: no cover - windows only
    """DEVMODEs to try, from the most complete to none at all (driver defaults)."""
    import win32print

    handle = win32print.OpenPrinter(name)
    try:
        base = None
        for level in (9, 8, 2):  # per-user defaults first, then global defaults
            try:
                base = win32print.GetPrinter(handle, level)["pDevMode"]
            except Exception:  # noqa: BLE001
                base = None
            if base is not None:
                break
        candidates = []
        if base is not None:
            for full in (True, False):
                dm = _copy_devmode(win32print, handle, name, base)
                dm.Orientation = _DMORIENT_LANDSCAPE if landscape else _DMORIENT_PORTRAIT
                dm.Duplex = _DMDUP_HORIZONTAL if opts.duplex else _DMDUP_SIMPLEX
                dm.Fields |= _DM_ORIENTATION | _DM_DUPLEX
                dm.Copies = 1  # copies are sent as repeated pages, which works with every driver
                dm.Fields |= _DM_COPIES
                if full:
                    dm.PaperSize = _DMPAPER[opts.paper]
                    dm.Fields |= _DM_PAPERSIZE
                try:  # let the driver validate and merge its private settings
                    win32print.DocumentProperties(0, handle, name, dm, dm, _DM_IN_BUFFER | _DM_OUT_BUFFER)
                except Exception:  # noqa: BLE001
                    pass
                candidates.append(dm)
        candidates.append(None)
        return candidates
    finally:
        win32print.ClosePrinter(handle)


def _copy_devmode(win32print, handle, name: str, dm):  # pragma: no cover - windows only
    """Independent copy of a DEVMODE (fresh one from the driver, then the given values)."""
    try:
        fresh = win32print.GetPrinter(handle, 2)["pDevMode"]
        if fresh is None:
            return dm
        win32print.DocumentProperties(0, handle, name, fresh, dm, _DM_IN_BUFFER | _DM_OUT_BUFFER)
        return fresh
    except Exception:  # noqa: BLE001
        return dm


def _print_windows(doc: fitz.Document, opts: PrintOptions) -> Optional[str]:  # pragma: no cover - windows only
    try:
        import win32gui
        import win32print
        from PIL import Image
    except ImportError as exc:
        raise PrintError(t("prn.no_pywin32")) from exc
    ctypes, gdi32, DOCINFOW, BITMAPINFOHEADER = _gdi()

    name = opts.printer or win32print.GetDefaultPrinter()
    first = doc[0].rect
    landscape = first.width > first.height
    errors: list[str] = []
    candidates = _devmodes(name, landscape, opts)

    for attempt, devmode in enumerate(candidates):
        try:
            hdc = win32gui.CreateDC("WINSPOOL", name, devmode)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"CreateDC: {exc}")
            continue
        started = False
        printed = 0
        try:
            info = DOCINFOW(ctypes.sizeof(DOCINFOW), opts.title, opts.output_file, None, 0)
            if gdi32.StartDocW(hdc, ctypes.byref(info)) <= 0:
                errors.append(_win_error(ctypes, "StartDoc failed"))
                continue
            started = True
            dpi = min(opts.dpi, max(72, gdi32.GetDeviceCaps(hdc, _LOGPIXELSX)))
            phys_w, phys_h = gdi32.GetDeviceCaps(hdc, _PHYSICALWIDTH), gdi32.GetDeviceCaps(hdc, _PHYSICALHEIGHT)
            off_x, off_y = gdi32.GetDeviceCaps(hdc, _PHYSICALOFFSETX), gdi32.GetDeviceCaps(hdc, _PHYSICALOFFSETY)
            gdi32.SetStretchBltMode(hdc, _HALFTONE)
            gdi32.SetBrushOrgEx(hdc, 0, 0, None)
            pages = [doc[i] for i in range(len(doc))] * max(1, opts.copies)
            for index, page in enumerate(pages):
                if gdi32.StartPage(hdc) <= 0:
                    raise PrintError(_win_error(ctypes, "StartPage failed"))
                pix = page.get_pixmap(dpi=dpi, alpha=False)
                img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                stride = (img.width * 3 + 3) & ~3
                bits = img.tobytes("raw", "BGR", stride, 1)
                bmi = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), img.width, -img.height, 1, 24, 0,
                                       len(bits), 0, 0, 0, 0)
                # Whole PDF page onto the physical sheet: the DC origin is the printable-area corner.
                if gdi32.StretchDIBits(hdc, -off_x, -off_y, phys_w, phys_h, 0, 0, img.width, img.height,
                                       bits, ctypes.byref(bmi), _DIB_RGB_COLORS, _SRCCOPY) == 0:
                    raise PrintError(_win_error(ctypes, f"Drawing page {index + 1} failed"))
                if gdi32.EndPage(hdc) <= 0:
                    raise PrintError(_win_error(ctypes, "EndPage failed"))
                printed += 1
            if gdi32.EndDoc(hdc) <= 0:
                raise PrintError(_win_error(ctypes, "EndDoc failed"))
            started = False
            if devmode is None or attempt > 0:
                return t("prn.fallback_settings")
            return None
        except PrintError as exc:
            errors.append(str(exc))
            # Retry with simpler settings only when nothing was printed yet.
            if printed:
                break
        finally:
            if started:
                gdi32.AbortDoc(hdc)
            gdi32.DeleteDC(hdc)
    raise PrintError(t("prn.failed", error=" / ".join(errors)) + "\n\n" + t("prn.try_pdf"))


def open_with_system_viewer(path: str | os.PathLike) -> None:
    path = str(Path(path))
    if IS_WINDOWS:
        os.startfile(path)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])
