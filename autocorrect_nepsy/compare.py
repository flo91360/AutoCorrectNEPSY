"""Comparaison d'une correction automatique avec celle de l'ergothérapeute."""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from pathlib import Path

from .criteria import CODES, PROCESS_NAMES
from .report import FIELD_BY_CODE


# Les processus de la NEPSY-II et leurs critères.
PROCESSES = {"Général": ("G",), "Motricité": ("A", "B"), "Global": ("C", "D"),
             "Local": ("E", "F")}


@dataclass
class Pair:
    item: int
    code: str
    auto: int
    reference: int
    flagged: bool = False  # item signalé « à vérifier » par la correction automatique


def _rows(path: str | Path) -> tuple[dict[str, str], list[tuple[int, dict[str, str]]], str]:
    """Colonnes (nom en minuscules -> nom lu) et lignes d'un CSV de cotation,
    avec leur numéro d'item ; les lignes sans numéro d'item sont écartées."""
    path = Path(path)
    if not path.is_file():
        raise ValueError(f"{path} : fichier introuvable")
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1252")
    header = text.splitlines()[0] if text else ""
    reader = csv.DictReader(io.StringIO(text), delimiter=max(",;\t", key=header.count))
    columns = {name.strip().lower(): name for name in reader.fieldnames or [] if name}
    if "item" not in columns:
        raise ValueError(f"{path.name} : colonne « item » absente (première ligne : {header!r})")
    rows = []
    for row in reader:
        item = (row.get(columns["item"]) or "").strip()
        if item.isdigit():
            rows.append((int(item), row))
    return columns, rows, path.name


def read_scores(path: str | Path) -> dict[int, dict[str, int]]:
    """Lit un CSV de cotation (colonnes ``item``, ``general``, ``motricite_A``…).

    Accepte aussi un tableau enregistré par Excel : séparateur point-virgule,
    encodage Windows, marque d'ordre des octets en tête du fichier. Les lignes
    sans numéro d'item (total, ligne vide) sont ignorées. Un fichier absent ou
    illisible lève ``ValueError`` avec un message lisible.
    """
    columns, rows, name = _rows(path)
    scores: dict[int, dict[str, int]] = {}
    for item, row in rows:
        found: dict[str, int] = {}
        for code, field in FIELD_BY_CODE.items():
            column = columns.get(field.lower())
            value = (row.get(column) or "").strip() if column else ""
            if not value:
                continue
            if value not in ("0", "1"):
                raise ValueError(f"{name} : note « {value} » illisible (item {item}, "
                                 f"colonne {field}, 0 ou 1 attendu)")
            found[code] = int(value)
        scores[item] = found
    return scores


def read_flags(path: str | Path) -> set[int] | None:
    """Items signalés « à vérifier » dans un cotation.csv de la correction
    automatique (colonne ``a_verifier``), ``None`` si la colonne est absente."""
    columns, rows, _ = _rows(path)
    column = columns.get("a_verifier")
    if column is None:
        return None
    return {item for item, row in rows if (row.get(column) or "").strip().lower() == "oui"}


def pair_scores(auto: dict[int, dict[str, int]], reference: dict[int, dict[str, int]],
                flagged: set[int] | None = None) -> list[Pair]:
    flagged = flagged or set()
    pairs = []
    for item in sorted(set(auto) & set(reference)):
        for code in CODES:
            if code in auto[item] and code in reference[item]:
                pairs.append(Pair(item, code, auto[item][code], reference[item][code],
                                  item in flagged))
    return pairs


def cohen_kappa(pairs: list[Pair]) -> float | None:
    """Kappa de Cohen sur des notes 0/1 (accord corrigé du hasard)."""
    n = len(pairs)
    if n == 0:
        return None
    observed = sum(p.auto == p.reference for p in pairs) / n
    p_auto = sum(p.auto for p in pairs) / n
    p_ref = sum(p.reference for p in pairs) / n
    expected = p_auto * p_ref + (1 - p_auto) * (1 - p_ref)
    if expected >= 1:
        return 1.0 if observed == 1 else None
    return (observed - expected) / (1 - expected)


def format_kappa(kappa: float | None) -> str:
    """Kappa au format français ; « – » s'il n'est pas calculable (notes
    toutes identiques des deux côtés)."""
    return "–" if kappa is None else f"{kappa:.2f}".replace(".", ",")


def format_comparison(pairs: list[Pair], flags_known: bool = False) -> str:
    """Accord, kappa (global et par critère) et liste des désaccords.
    ``flags_known`` : les items « à vérifier » de la correction automatique sont
    connus (``Pair.flagged``), la part des désaccords signalés est affichée."""
    if not pairs:
        return "Aucun item commun aux deux cotations."
    agree = sum(p.auto == p.reference for p in pairs)
    lines = [f"Accord global : {agree}/{len(pairs)} critères ({agree / len(pairs):.0%})",
             f"Kappa de Cohen : {format_kappa(cohen_kappa(pairs))}"]
    disagreements = [p for p in pairs if p.auto != p.reference]
    if flags_known and disagreements:
        flagged = sum(p.flagged for p in disagreements)
        lines.append(f"Désaccords dans un item signalé « à vérifier » : "
                     f"{flagged}/{len(disagreements)}")
    lines.append("")
    lines.append("Par critère (accord, kappa) :")
    for code in CODES:
        subset = [p for p in pairs if p.code == code]
        if subset:
            ok = sum(p.auto == p.reference for p in subset)
            lines.append(f"  {PROCESS_NAMES[code]:<12} {ok}/{len(subset)}  "
                         f"kappa {format_kappa(cohen_kappa(subset))}")
    if disagreements:
        lines.append("")
        lines.append("Désaccords (automatique / ergothérapeute) :")
        for p in disagreements:
            mark = "  (à vérifier)" if flags_known and p.flagged else ""
            lines.append(f"  item {p.item:>2}  {PROCESS_NAMES[p.code]:<12} {p.auto} / "
                         f"{p.reference}{mark}")
    return "\n".join(lines)
