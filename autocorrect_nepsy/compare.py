"""Comparaison d'une correction automatique avec celle de l'ergothérapeute."""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from pathlib import Path

from .criteria import CODES, PROCESS_NAMES
from .report import FIELD_BY_CODE


@dataclass
class Pair:
    item: int
    code: str
    auto: int
    reference: int


def read_scores(path: str | Path) -> dict[int, dict[str, int]]:
    """Lit un CSV de cotation (colonnes ``item``, ``general``, ``motricite_A``…).

    Accepte aussi un tableau enregistré par Excel : séparateur point-virgule,
    encodage Windows, marque d'ordre des octets en tête du fichier. Les lignes
    sans numéro d'item (total, ligne vide) sont ignorées. Un fichier absent ou
    illisible lève ``ValueError`` avec un message lisible.
    """
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
    scores: dict[int, dict[str, int]] = {}
    for row in reader:
        item = (row.get(columns["item"]) or "").strip()
        if not item.isdigit():
            continue
        found: dict[str, int] = {}
        for code, name in FIELD_BY_CODE.items():
            column = columns.get(name.lower())
            value = (row.get(column) or "").strip() if column else ""
            if not value:
                continue
            if value not in ("0", "1"):
                raise ValueError(f"{path.name} : note « {value} » illisible (item {item}, "
                                 f"colonne {name}, 0 ou 1 attendu)")
            found[code] = int(value)
        scores[int(item)] = found
    return scores


def pair_scores(auto: dict[int, dict[str, int]],
                reference: dict[int, dict[str, int]]) -> list[Pair]:
    pairs = []
    for item in sorted(set(auto) & set(reference)):
        for code in CODES:
            if code in auto[item] and code in reference[item]:
                pairs.append(Pair(item, code, auto[item][code], reference[item][code]))
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


def format_comparison(pairs: list[Pair]) -> str:
    if not pairs:
        return "Aucun item commun aux deux cotations."
    agree = sum(p.auto == p.reference for p in pairs)
    lines = [f"Accord global : {agree}/{len(pairs)} critères ({agree / len(pairs):.0%})"]
    kappa = cohen_kappa(pairs)
    if kappa is not None:
        lines.append(f"Kappa de Cohen : {kappa:.2f}")
    lines.append("")
    lines.append("Par critère :")
    for code in CODES:
        subset = [p for p in pairs if p.code == code]
        if subset:
            ok = sum(p.auto == p.reference for p in subset)
            lines.append(f"  {PROCESS_NAMES[code]:<12} {ok}/{len(subset)}")
    disagreements = [p for p in pairs if p.auto != p.reference]
    if disagreements:
        lines.append("")
        lines.append("Désaccords (automatique / ergothérapeute) :")
        for p in disagreements:
            lines.append(f"  item {p.item:>2}  {PROCESS_NAMES[p.code]:<12} {p.auto} / {p.reference}")
    return "\n".join(lines)
