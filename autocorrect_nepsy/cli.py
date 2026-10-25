"""Ligne de commande : ``autocorrect-nepsy corriger`` et ``autocorrect-nepsy comparer``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .compare import format_comparison, pair_scores, read_scores
from .ink import INK_HUES
from .layout import LayoutError
from .pipeline import correct, page_label
from .report import save_results, summary_text


def _pages(text: str) -> list[int]:
    try:
        pages = [int(p) for p in text.split(",")]
    except ValueError:
        raise argparse.ArgumentTypeError("exemple attendu : 1,2,3") from None
    if any(not 1 <= p <= 6 for p in pages):
        raise argparse.ArgumentTypeError("les pages du cahier vont de 1 à 6")
    return pages


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="autocorrect-nepsy",
        description="Correction automatique du subtest Copie de figures (NEPSY-II), prototype.")
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser("corriger", help="corrige des pages scannées du cahier de réponses")
    run.add_argument("fichiers", nargs="+", type=Path, help="scans (PDF ou images)")
    run.add_argument("--pages", type=_pages,
                     help="numéro de page du cahier (1 à 6) de chaque page scannée, dans l'ordre, "
                          "ex. 1,2,3 (par défaut, déduit des scans pris dans l'ordre du cahier)")
    run.add_argument("-o", "--sortie", type=Path, default=Path("correction"),
                     help="dossier de sortie (cotation.csv et rapport.html)")
    run.add_argument("--encre", default="bleu", choices=sorted(INK_HUES),
                     help="couleur du stylo de l'enfant")
    run.add_argument("--dpi", type=float, help="résolution du scan si elle n'est pas lisible")

    cmp = commands.add_parser("comparer", help="compare la correction automatique à celle de l'ergo")
    cmp.add_argument("automatique", type=Path, help="cotation.csv produit par « corriger »")
    cmp.add_argument("reference", type=Path, help="cotation de l'ergothérapeute (même format)")

    args = parser.parse_args(argv)
    if args.command == "comparer":
        try:
            pairs = pair_scores(read_scores(args.automatique), read_scores(args.reference))
        except ValueError as error:
            print(f"Erreur : {error}", file=sys.stderr)
            return 1
        print(format_comparison(pairs))
        return 0

    try:
        correction = correct(args.fichiers, args.pages, args.encre, args.dpi)
    except (LayoutError, ValueError) as error:
        print(f"Erreur : {error}", file=sys.stderr)
        return 1
    save_results(correction, args.sortie)
    for source, number in correction.pages:
        print(f"{source} : {page_label(number)}")
    print()
    print(summary_text(correction))
    print(f"\nRésultats écrits dans {args.sortie}/ (cotation.csv, rapport.html)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
