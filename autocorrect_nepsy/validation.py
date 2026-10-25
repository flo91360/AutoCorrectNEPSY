"""Validation sur un corpus local : correction automatique comparée à la
cotation de l'ergothérapeute, protocole par protocole, puis chiffres d'ensemble.

Le corpus reste sur l'ordinateur de l'ergothérapeute (données de santé de
mineurs, à ranger par exemple dans ``donnees/``, ignoré par git) : un dossier
par protocole, nommé par un pseudonyme (P001…), avec

- les scans du cahier (PDF ou images), triés dans l'ordre naturel des noms ;
- ``cotation_ergo.csv`` : la cotation de l'ergothérapeute, faite sans voir la
  proposition de l'outil (même format que ``cotation.csv``) ;
- ``pages.txt`` (facultatif) : le numéro de page du cahier de chaque scan,
  ex. « 1,2,3,4,5,6 », quand il ne peut pas être deviné.

Seuls des chiffres d'ensemble sont affichés. Le fichier JSON facultatif garde
aussi la cotation automatique de chaque protocole, pour comparer deux versions
de l'outil sur le même corpus : il reste lui aussi sur l'ordinateur.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import __version__
from .compare import PROCESSES, Pair, cohen_kappa, format_kappa, pair_scores, read_scores
from .criteria import PROCESS_NAMES
from .layout import LayoutError
from .pipeline import correct
from .scan import SCAN_SUFFIXES, natural_key

REFERENCE_NAME = "cotation_ergo.csv"
PAGES_NAME = "pages.txt"

# Objectifs proposés par l'audit pour un usage clinique assisté, à fixer avec
# l'ergothérapeute.
MIN_PROCESS_KAPPA = 0.80  # kappa de chaque processus
MIN_ITEM_AGREEMENT = 0.85  # accord de chaque item
MIN_FLAGGED_DISAGREEMENTS = 0.95  # part des désaccords dans des items « à vérifier »
TOTAL_TOLERANCE = 1  # écart toléré sur le total d'un processus (points)
MIN_TOTALS_WITHIN = 0.90  # part des protocoles dont chaque total est dans la tolérance

Scores = dict[int, dict[str, int]]


@dataclass
class Protocol:
    """Un protocole du corpus, corrigé automatiquement."""

    name: str
    auto: Scores
    reference: Scores
    flagged: set[int] = field(default_factory=set)  # items « à vérifier »

    @property
    def pairs(self) -> list[Pair]:
        return pair_scores(self.auto, self.reference, self.flagged)


def protocol_folders(corpus: Path) -> list[Path]:
    """Dossiers de protocole du corpus : ceux qui contiennent une cotation de
    l'ergothérapeute."""
    return sorted((p for p in corpus.iterdir() if (p / REFERENCE_NAME).is_file()),
                  key=natural_key)


def load_protocol(folder: Path, ink: str = "bleu") -> Protocol:
    """Corrige les scans d'un protocole et lit la cotation de l'ergothérapeute.
    Lève ``ValueError`` (ou ``LayoutError``) avec un message lisible."""
    scans = sorted((p for p in folder.iterdir() if p.suffix.lower() in SCAN_SUFFIXES),
                   key=natural_key)
    if not scans:
        raise ValueError("aucun scan dans le dossier")
    pages = None
    if (folder / PAGES_NAME).is_file():
        text = (folder / PAGES_NAME).read_text(encoding="utf-8").strip()
        try:
            pages = [int(p) for p in text.replace(";", ",").split(",")]
        except ValueError:
            raise ValueError(f"{PAGES_NAME} illisible ({text!r}), exemple attendu : 1,2,3") from None
    try:
        correction = correct(scans, pages, ink)
    except ValueError as error:
        if "--pages" in str(error):
            raise ValueError(f"{error} ; dans un corpus, l'indiquer dans {PAGES_NAME}") from None
        raise
    auto = {report.item: {code: c.score for code, c in report.result.criteria.items()}
            for report in correction.items}
    flagged = {report.item for report in correction.items if report.result.to_review}
    return Protocol(folder.name, auto, read_scores(folder / REFERENCE_NAME), flagged)


def run(corpus: str | Path, ink: str = "bleu",
        progress: Callable[[str], None] | None = None) -> tuple[list[Protocol], list[str]]:
    """Corrige chaque protocole du corpus. Renvoie les protocoles corrigés et
    les erreurs (« P003 : … ») des protocoles qui n'ont pas pu l'être."""
    corpus = Path(corpus)
    if not corpus.is_dir():
        raise ValueError(f"{corpus} : dossier introuvable")
    protocols, errors = [], []
    for folder in protocol_folders(corpus):
        try:
            protocols.append(load_protocol(folder, ink))
        except (LayoutError, ValueError) as error:
            errors.append(f"{folder.name} : {error}")
            if progress:
                progress(f"{folder.name} : non corrigé ({error})")
            continue
        if progress:
            progress(f"{folder.name} : {len(protocols[-1].auto)} item(s) corrigé(s)")
    return protocols, errors


def _agreement(pairs: list[Pair]) -> dict:
    agree = sum(p.auto == p.reference for p in pairs)
    return {"criteres": len(pairs), "accord": agree / len(pairs) if pairs else None,
            "kappa": cohen_kappa(pairs)}


def _total(scores: Scores, items: set[int], codes: tuple[str, ...]) -> int:
    return sum(scores[item].get(code, 0) for item in items for code in codes)


def summarize(protocols: list[Protocol]) -> dict:
    """Chiffres d'ensemble du corpus (et cotation automatique de chaque protocole)."""
    pairs = [pair for protocol in protocols for pair in protocol.pairs]
    disagreements = [p for p in pairs if p.auto != p.reference]
    items = [(protocol, item) for protocol in protocols
             for item in set(protocol.auto) & set(protocol.reference)]
    # Écart du total de chaque processus, protocole par protocole.
    gaps = []
    for protocol in protocols:
        common = set(protocol.auto) & set(protocol.reference)
        gaps.append({name: abs(_total(protocol.auto, common, codes)
                               - _total(protocol.reference, common, codes))
                     for name, codes in PROCESSES.items()})
    totals = {}
    for name in PROCESSES:
        values = [gap[name] for gap in gaps]
        totals[name] = {"ecart_moyen": sum(values) / len(values) if values else None,
                        "dans_la_tolerance": (sum(v <= TOTAL_TOLERANCE for v in values)
                                              / len(values) if values else None)}
    within = [all(v <= TOTAL_TOLERANCE for v in gap.values()) for gap in gaps]
    by_item = {}
    for item in sorted({item for _, item in items}):
        by_item[item] = _agreement([p for p in pairs if p.item == item])
    summary = {
        "version": __version__,
        "protocoles": len(protocols),
        "items": len(items),
        "ensemble": _agreement(pairs),
        "par_processus": {name: _agreement([p for p in pairs if p.code in codes])
                          for name, codes in PROCESSES.items()},
        "par_critere": {code: _agreement([p for p in pairs if p.code == code])
                        for code in PROCESS_NAMES},
        "par_item": by_item,
        "totaux": totals,
        "a_verifier": {
            "items_signales": (sum(item in protocol.flagged for protocol, item in items) / len(items)
                               if items else None),
            "desaccords": len(disagreements),
            "desaccords_signales": sum(p.flagged for p in disagreements),
        },
        "cotations": {protocol.name: {str(item): scores for item, scores in protocol.auto.items()}
                      for protocol in protocols},
    }
    flagged_share = (summary["a_verifier"]["desaccords_signales"] / len(disagreements)
                     if disagreements else 1.0)
    kappas = [v["kappa"] for v in summary["par_processus"].values() if v["criteres"]]
    item_agreements = [v["accord"] for v in by_item.values() if v["criteres"]]
    summary["objectifs"] = [
        {"objectif": f"kappa de chaque processus ≥ {MIN_PROCESS_KAPPA:.2f}".replace(".", ","),
         "atteint": bool(kappas) and all(k is not None and k >= MIN_PROCESS_KAPPA for k in kappas)},
        {"objectif": f"accord de chaque item ≥ {MIN_ITEM_AGREEMENT:.0%}",
         "atteint": bool(item_agreements) and min(item_agreements) >= MIN_ITEM_AGREEMENT},
        {"objectif": f"au moins {MIN_FLAGGED_DISAGREEMENTS:.0%} des désaccords dans des items "
                     "« à vérifier »",
         "atteint": flagged_share >= MIN_FLAGGED_DISAGREEMENTS},
        {"objectif": f"tous les totaux à {TOTAL_TOLERANCE} point près dans au moins "
                     f"{MIN_TOTALS_WITHIN:.0%} des protocoles",
         "atteint": bool(within) and sum(within) / len(within) >= MIN_TOTALS_WITHIN},
    ]
    return summary


def _percent(value: float | None) -> str:
    return "–" if value is None else f"{value:.0%}".replace("%", " %")


def compare_versions(current: dict, previous: dict, protocols: list[Protocol]) -> str:
    """Critères dont la cotation automatique a changé depuis un passage
    précédent (même corpus), et s'ils se rapprochent ou s'éloignent de
    l'ergothérapeute."""
    reference = {p.name: p.reference for p in protocols}
    changed = closer = farther = 0
    for name, items in current["cotations"].items():
        before = previous.get("cotations", {}).get(name, {})
        for item, scores in items.items():
            for code, value in scores.items():
                old = before.get(item, {}).get(code)
                if old is None or old == value:
                    continue
                changed += 1
                ergo = reference.get(name, {}).get(int(item), {}).get(code)
                if ergo == value:
                    closer += 1
                elif ergo == old:
                    farther += 1
    return (f"Depuis la version {previous.get('version', '?')} : {changed} critère(s) changent, "
            f"dont {closer} se rapprochent de l'ergothérapeute et {farther} s'en éloignent.")


def format_summary(summary: dict) -> str:
    lines = [f"Validation (version {summary['version']}) : {summary['protocoles']} protocole(s), "
             f"{summary['items']} item(s), {summary['ensemble']['criteres']} critère(s) comparés.",
             f"Accord global : {_percent(summary['ensemble']['accord'])}, "
             f"kappa {format_kappa(summary['ensemble']['kappa'])}", "",
             "Par processus (accord, kappa, écart moyen du total, totaux à "
             f"{TOTAL_TOLERANCE} point près) :"]
    for name, values in summary["par_processus"].items():
        total = summary["totaux"][name]
        mean = "–" if total["ecart_moyen"] is None else f"{total['ecart_moyen']:.1f}".replace(".", ",")
        lines.append(f"  {name:<10} {_percent(values['accord']):>6}  kappa "
                     f"{format_kappa(values['kappa']):>5}  écart {mean:>4}  "
                     f"{_percent(total['dans_la_tolerance'])}")
    lines += ["", "Par critère (accord, kappa) :"]
    for code, values in summary["par_critere"].items():
        if values["criteres"]:
            lines.append(f"  {PROCESS_NAMES[code]:<12} {_percent(values['accord']):>6}  kappa "
                         f"{format_kappa(values['kappa'])}")
    weak = [(item, v) for item, v in summary["par_item"].items()
            if v["criteres"] and v["accord"] < MIN_ITEM_AGREEMENT]
    lines += ["", f"Items sous {MIN_ITEM_AGREEMENT:.0%} d'accord : "
              + (", ".join(f"{item} ({_percent(v['accord'])})" for item, v in weak) or "aucun")]
    review = summary["a_verifier"]
    lines += [f"Items signalés « à vérifier » : {_percent(review['items_signales'])} ; "
              f"désaccords dans un item signalé : {review['desaccords_signales']}/"
              f"{review['desaccords']}", "", "Objectifs :"]
    lines += [f"  {'atteint' if o['atteint'] else 'NON ATTEINT':<11} {o['objectif']}"
              for o in summary["objectifs"]]
    return "\n".join(lines)


def save(summary: dict, path: str | Path) -> None:
    Path(path).write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")


def load(path: str | Path) -> dict:
    path = Path(path)
    if not path.is_file():
        raise ValueError(f"{path} : fichier introuvable")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"{path.name} : résultats de validation illisibles ({error})") from None
