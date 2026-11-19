"""Entry point: GUI by default, command line when an output or --print is given."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .imposition import PAPER_SIZES, Binding, ImposeOptions, impose, split_sides


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="booklet-printer",
        description="Met en page un PDF ou un PPTX en livret (cahier piqué) et l'imprime.",
    )
    p.add_argument("input", nargs="?", help="fichier source (.pdf, .pptx, …)")
    p.add_argument("-o", "--output", help="PDF imposé à écrire (mode ligne de commande)")
    p.add_argument("--print", dest="do_print", action="store_true", help="imprimer directement")
    p.add_argument("--printer", help="nom de l'imprimante (défaut : imprimante par défaut)")
    p.add_argument("--copies", type=int, default=1)
    p.add_argument("--paper", choices=list(PAPER_SIZES), default="A4")
    p.add_argument("--binding", choices=[b.value for b in Binding], default="auto")
    p.add_argument("--margin", type=float, default=5.0, help="marge en mm (défaut 5)")
    p.add_argument("--gutter", type=float, default=0.0, help="gouttière au pli en mm (défaut 0)")
    p.add_argument("--keep-back-cover", action="store_true", help="dernière page en 4e de couverture")
    p.add_argument("--fold-marks", action="store_true", help="ajouter des traits de pliage")
    p.add_argument("--split", action="store_true", help="avec -o : écrire aussi -rectos.pdf et -versos.pdf")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if not args.output and not args.do_print:
        from .gui import run

        run(args.input)
        return 0

    if not args.input:
        print("Erreur : fichier source manquant.", file=sys.stderr)
        return 2

    from .convert import load_document

    try:
        src = load_document(args.input)
    except Exception as exc:  # noqa: BLE001
        print(f"Erreur : {exc}", file=sys.stderr)
        return 1
    opts = ImposeOptions(
        paper=args.paper,
        binding=Binding(args.binding),
        margin_mm=args.margin,
        gutter_mm=args.gutter,
        keep_back_cover=args.keep_back_cover,
        fold_marks=args.fold_marks,
    )
    result = impose(src, opts)
    print(
        f"{result.source_pages} pages -> {len(result.sheets)} feuille(s), "
        f"{result.blank_pages} page(s) blanche(s), reliure {result.binding.value}"
    )
    if args.output:
        out = Path(args.output)
        result.document.save(out, garbage=3, deflate=True)
        print(f"Écrit : {out}")
        if args.split:
            rectos, versos = split_sides(result.document)
            rectos.save(out.with_name(out.stem + "-rectos.pdf"))
            versos.save(out.with_name(out.stem + "-versos.pdf"))
    if args.do_print:
        from .printing import PrintOptions, print_document

        print_document(
            result.document,
            PrintOptions(printer=args.printer, copies=args.copies, paper=args.paper, title=Path(args.input).name),
        )
        print("Envoyé à l'imprimante (recto-verso, bord court).")
    return 0
