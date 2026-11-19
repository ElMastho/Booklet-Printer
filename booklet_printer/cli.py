"""Entry point: GUI by default, command line when an output or --print is given."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .i18n import set_language, t
from .imposition import PAPER_SIZES, Binding, ImposeOptions, impose, render_reading_order, split_sides
from .pages import parse_page_list


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="booklet-printer", description=t("cli.description"))
    p.add_argument("input", nargs="?", help=t("cli.input"))
    p.add_argument("-o", "--output", help=t("cli.output"))
    p.add_argument("--print", dest="do_print", action="store_true", help=t("cli.print"))
    p.add_argument("--printer", help=t("cli.printer"))
    p.add_argument("--copies", type=int, default=1)
    p.add_argument("--paper", choices=list(PAPER_SIZES), default="A4")
    p.add_argument("--binding", choices=[b.value for b in Binding], default="auto")
    p.add_argument("--margin", type=float, default=5.0, help=t("cli.margin"))
    p.add_argument("--gutter", type=float, default=0.0, help=t("cli.gutter"))
    p.add_argument("--pages", help=t("cli.pages"))
    p.add_argument("--keep-back-cover", action="store_true", help=t("cli.keep_back_cover"))
    p.add_argument("--fold-marks", action="store_true", help=t("cli.fold_marks"))
    p.add_argument("--split", action="store_true", help=t("cli.split"))
    p.add_argument("--export-pages", metavar="PDF", help=t("cli.export_pages"))
    p.add_argument("--lang", choices=["auto", "en", "fr"], help=t("cli.lang"))
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    # Apply --lang before building the parser so that --help is translated too.
    if "--lang" in argv:
        i = argv.index("--lang")
        if i + 1 < len(argv):
            set_language(argv[i + 1])
    args = build_parser().parse_args(argv)

    if not args.output and not args.do_print and not args.export_pages:
        from .ui import run

        run(args.input)
        return 0

    if not args.input:
        print(t("cli.missing_input"), file=sys.stderr)
        return 2

    from .convert import load_document

    try:
        src = load_document(args.input)
        plan = parse_page_list(args.pages, len(src)) if args.pages else None
    except Exception as exc:  # noqa: BLE001
        print(t("cli.error", error=exc), file=sys.stderr)
        return 1
    opts = ImposeOptions(
        paper=args.paper,
        binding=Binding(args.binding),
        margin_mm=args.margin,
        gutter_mm=args.gutter,
        keep_back_cover=args.keep_back_cover,
        fold_marks=args.fold_marks,
    )
    result = impose(src, opts, plan)
    print(
        t(
            "cli.summary",
            pages=result.content_pages,
            sheets=len(result.sheets),
            blanks=result.padding_pages,
            binding=result.binding.value,
        )
    )
    if args.export_pages:
        render_reading_order(src, result.plan, opts).save(args.export_pages, garbage=3, deflate=True)
        print(t("cli.written", path=args.export_pages))
    if args.output:
        out = Path(args.output)
        result.document.save(out, garbage=3, deflate=True)
        print(t("cli.written", path=out))
        if args.split:
            fronts, backs = split_sides(result.document)
            fronts.save(out.with_name(out.stem + "-fronts.pdf"))
            backs.save(out.with_name(out.stem + "-backs.pdf"))
    if args.do_print:
        from .printing import PrintOptions, print_document

        print_document(
            result.document,
            PrintOptions(printer=args.printer, copies=args.copies, paper=args.paper, title=Path(args.input).name),
        )
        print(t("cli.sent"))
    return 0
