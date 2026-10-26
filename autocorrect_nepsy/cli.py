"""Ligne de commande : ``autocorrect-nepsy corriger``, ``comparer``, ``valider`` et
``seuils``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import validation
from .compare import format_comparison, pair_scores, read_flags, read_scores
from .criteria import CODES, PROCESS_NAMES, SUPPORTED_ITEMS, all_manual_thresholds
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
    run.add_argument("--enfant", default="",
                     help="pseudonyme ou initiales de l'enfant, repris dans le rapport")
    run.add_argument("--passation", default="", help="date de passation, reprise dans le rapport")

    cmp = commands.add_parser("comparer", help="compare la correction automatique à celle de l'ergo")
    cmp.add_argument("automatique", type=Path, help="cotation.csv produit par « corriger »")
    cmp.add_argument("reference", type=Path, help="cotation de l'ergothérapeute (même format)")

    val = commands.add_parser(
        "valider", help="compare l'outil à l'ergothérapeute sur un corpus local de protocoles")
    val.add_argument("corpus", type=Path,
                     help="dossier du corpus : un sous-dossier par protocole, avec ses scans et "
                          "cotation_ergo.csv (et pages.txt si besoin)")
    val.add_argument("--encre", default="bleu", choices=sorted(INK_HUES),
                     help="couleur du stylo des enfants")
    val.add_argument("--json", type=Path,
                     help="enregistre les résultats (à garder hors du dépôt : ils contiennent la "
                          "cotation automatique de chaque protocole)")
    val.add_argument("--precedent", type=Path,
                     help="résultats JSON d'un passage précédent, pour voir ce qui a changé")

    thr = commands.add_parser("seuils", help="liste les seuils du manuel utilisés par l'outil")
    thr.add_argument("--item", type=int, choices=SUPPORTED_ITEMS, metavar="N",
                     help="seulement les seuils de cet item")

    args = parser.parse_args(argv)
    if args.command == "valider":
        return _validate(args)
    if args.command == "seuils":
        print(format_thresholds(args.item))
        return 0
    if args.command == "comparer":
        try:
            flags = read_flags(args.automatique)
            pairs = pair_scores(read_scores(args.automatique), read_scores(args.reference), flags)
        except ValueError as error:
            print(f"Erreur : {error}", file=sys.stderr)
            return 1
        print(format_comparison(pairs, flags_known=flags is not None))
        return 0

    try:
        correction = correct(args.fichiers, args.pages, args.encre, args.dpi)
    except (LayoutError, ValueError) as error:
        print(f"Erreur : {error}", file=sys.stderr)
        return 1
    correction.child, correction.session_date = args.enfant.strip(), args.passation.strip()
    save_results(correction, args.sortie)
    for source, number in correction.pages:
        print(f"{source} : {page_label(number)}")
    print()
    print(summary_text(correction))
    print(f"\nRésultats écrits dans {args.sortie}/ (cotation.csv, cotation_automatique.csv, "
          "rapport.html)")
    return 0


def format_thresholds(item: int | None = None) -> str:
    """Seuils du manuel, item par item : critère(s), valeur et description."""
    legend = ", ".join(f"{code} : {PROCESS_NAMES[code]}" for code in CODES)
    lines = ["Seuils du manuel NEPSY-II (reformulés) utilisés par l'outil, à vérifier sur le "
             "manuel.", f"Critères : {legend}.",
             "Les autres constantes du code sont des réglages internes de l'outil."]
    current = None
    entries = [e for e in all_manual_thresholds() if item is None or item in e.items]
    # Dans un item, dans l'ordre des critères de la feuille de cotation.
    entries.sort(key=lambda e: (e.items, CODES.index(e.threshold.codes[0])))
    for entry in entries:
        if entry.items != current:
            current = entry.items
            label = " et ".join(map(str, current))
            lines += ["", f"Item{'s' if len(current) > 1 else ''} {label}"]
        t = entry.threshold
        lines.append(f"  {' '.join(t.codes):<5}  {t.text:>7}  {t.description}")
    return "\n".join(lines)


def _validate(args: argparse.Namespace) -> int:
    try:
        previous = validation.load(args.precedent) if args.precedent else None
        protocols, errors = validation.run(args.corpus, args.encre, progress=print)
    except ValueError as error:
        print(f"Erreur : {error}", file=sys.stderr)
        return 1
    if not protocols:
        print("Erreur : aucun protocole corrigé (un dossier par protocole, avec "
              f"{validation.REFERENCE_NAME})", file=sys.stderr)
        return 1
    summary = validation.summarize(protocols)
    print()
    print(validation.format_summary(summary))
    if previous:
        print()
        print(validation.compare_versions(summary, previous, protocols))
    if errors:
        print(f"\n{len(errors)} protocole(s) non corrigé(s) :")
        print("\n".join(f"  {error}" for error in errors))
    if args.json:
        validation.save(summary, args.json)
        print(f"\nRésultats enregistrés dans {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
