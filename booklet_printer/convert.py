"""Load sources as PDF. PPTX/PPT/ODP/DOCX... are converted with LibreOffice."""

from __future__ import annotations

import glob
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pymupdf as fitz

OFFICE_EXTENSIONS = {".pptx", ".ppt", ".odp", ".pps", ".ppsx", ".docx", ".doc", ".odt"}
SUPPORTED_EXTENSIONS = {".pdf"} | OFFICE_EXTENSIONS


class ConversionError(RuntimeError):
    pass


def find_soffice() -> str | None:
    """Locate the LibreOffice executable (env var, PATH, usual install dirs)."""
    env = os.environ.get("BOOKLET_SOFFICE")
    if env and Path(env).exists():
        return env
    for name in ("soffice", "libreoffice"):
        found = shutil.which(name)
        if found:
            return found
    candidates: list[str] = []
    if sys.platform.startswith("win"):
        for base in filter(None, (os.environ.get("PROGRAMFILES"), os.environ.get("PROGRAMFILES(X86)"))):
            candidates += glob.glob(os.path.join(base, "LibreOffice*", "program", "soffice.exe"))
    elif sys.platform == "darwin":
        candidates.append("/Applications/LibreOffice.app/Contents/MacOS/soffice")
    else:
        candidates += ["/usr/bin/soffice", "/usr/lib/libreoffice/program/soffice", "/opt/libreoffice/program/soffice"]
        candidates += glob.glob("/opt/libreoffice*/program/soffice")
    for c in candidates:
        if Path(c).exists():
            return c
    return None


POWERPOINT_EXTENSIONS = {".pptx", ".ppt", ".pps", ".ppsx"}


def powerpoint_to_pdf(path: Path, out_dir: Path) -> Path:
    """Windows only: export through an installed Microsoft PowerPoint (COM)."""
    import pythoncom  # type: ignore[import-not-found]
    import win32com.client  # type: ignore[import-not-found]

    pdf = out_dir / (path.stem + ".pdf")
    pythoncom.CoInitialize()
    app = pres = None
    try:
        app = win32com.client.DispatchEx("PowerPoint.Application")
        # Open(FileName, ReadOnly, Untitled, WithWindow)
        pres = app.Presentations.Open(str(path.resolve()), True, False, False)
        pres.SaveAs(str(pdf.resolve()), 32)  # ppSaveAsPDF
    finally:
        if pres is not None:
            pres.Close()
        if app is not None:
            app.Quit()
        pythoncom.CoUninitialize()
    if not pdf.exists():
        raise ConversionError("PowerPoint n'a pas produit de PDF.")
    return pdf


def office_to_pdf(path: Path, out_dir: Path, timeout: int = 180) -> Path:
    soffice = find_soffice()
    if not soffice and sys.platform.startswith("win") and path.suffix.lower() in POWERPOINT_EXTENSIONS:
        try:
            return powerpoint_to_pdf(path, out_dir)
        except ConversionError:
            raise
        except Exception as exc:  # noqa: BLE001 - PowerPoint absent or COM failure
            raise ConversionError(
                "Ni LibreOffice ni Microsoft PowerPoint ne sont disponibles pour convertir "
                f"ce fichier ({exc}). Installez LibreOffice (https://www.libreoffice.org) "
                "ou exportez d'abord la présentation en PDF."
            ) from exc
    if not soffice:
        raise ConversionError(
            "LibreOffice est introuvable : il est nécessaire pour convertir les fichiers "
            f"{path.suffix}. Installez-le (https://www.libreoffice.org) ou exportez "
            "d'abord votre présentation en PDF depuis PowerPoint."
        )
    # A private profile avoids clashing with a LibreOffice window already open.
    profile = Path(tempfile.mkdtemp(prefix="booklet-lo-profile-"))
    cmd = [
        soffice,
        f"-env:UserInstallation={profile.as_uri()}",
        "--headless",
        "--norestore",
        "--convert-to",
        "pdf",
        "--outdir",
        str(out_dir),
        str(path),
    ]
    kwargs = {}
    if sys.platform.startswith("win"):
        kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, **kwargs)
    except subprocess.TimeoutExpired as exc:
        raise ConversionError("La conversion LibreOffice a pris trop de temps.") from exc
    finally:
        shutil.rmtree(profile, ignore_errors=True)
    pdf = out_dir / (path.stem + ".pdf")
    if proc.returncode != 0 or not pdf.exists():
        raise ConversionError(f"Échec de la conversion LibreOffice :\n{proc.stderr or proc.stdout}")
    return pdf


def load_document(path: str | os.PathLike) -> fitz.Document:
    """Open a PDF, or convert an office document to PDF, and return it in memory."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)
    ext = path.suffix.lower()
    if ext == ".pdf":
        return fitz.open(path)
    if ext in OFFICE_EXTENSIONS:
        with tempfile.TemporaryDirectory(prefix="booklet-") as tmp:
            pdf = office_to_pdf(path, Path(tmp))
            data = pdf.read_bytes()
        return fitz.open(stream=data, filetype="pdf")
    raise ConversionError(f"Format non pris en charge : {ext}")
