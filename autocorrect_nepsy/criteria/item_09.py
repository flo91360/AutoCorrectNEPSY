"""Item 9 : dix cercles pleins alignés en diagonale, montant de gauche à droite.

Seuils repris du manuel NEPSY-II (Copie de figures), reformulés.

Chaque marque est une tache d'encre d'un seul tenant, classée en point, tiret,
cercle vide ou cercle plein (un cercle partiellement plein compte comme plein).
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

import numpy as np

from .. import geometry as geo
from ..strokes import Blob, Drawing
from . import marks as mk
from .base import Checks, ItemResult, empty_result, fmt, not_recognized

POINT_MAX_MM = 1.2  # tache plus petite : simple point de stylo
# Un tiret est allongé et fin (épaisseur moyenne d'un trait de stylo) ; un
# cercle plein aplati reste plus épais. Très allongée, une tache est un tiret.
DASH_MIN_ELONGATION = 2.0
DASH_MAX_THICKNESS_MM = 1.0
DASH_ALWAYS_ELONGATION = 3.0
FILLED_MIN_SOLIDITY = 0.75  # encre / enveloppe convexe d'une tache pleine
EMPTY_MIN_HOLE = 0.2  # part non encrée à l'intérieur d'un cercle vide
MARK_MAX_MM = 10.0  # au-delà, ce n'est plus une marque mais un autre élément
ROW_DISTANCE_MM = 6.0  # marque plus éloignée de la ligne : hors de la rangée
DUST_MM = 1.0  # tache isolée plus petite, hors de la rangée : poussière, ignorée
GENERAL_COUNT = (9, 11)  # nombre de cercles pleins
GENERAL_MAX_DIAMETER_MM = 5.0
ANGLE_RANGE = (30.0, 60.0)  # Général et Global D, par rapport à l'horizontale
MOTOR_MAX_DIAMETER_MM = 3.0  # Motricité A : au plus la moitié des marques au-delà
GLOBAL_MIN_MARKS = 6  # Global C
LOCAL_COUNT = 10  # Local E
LOCAL_MIN_GAP_MM = 2.0  # Local E : écart bord à bord entre cercles voisins
LOCAL_MAX_GAP_MM = 5.0  # Local F
LOCAL_MAX_LENGTH_MM = 60.0  # Local F : du cercle le plus à gauche au plus à droite

FILLED, POINT, DASH, EMPTY = "cercle plein", "point", "tiret", "cercle vide"
SHORT_NAMES = {FILLED: "plein", POINT: "point", DASH: "tiret", EMPTY: "vide"}


@dataclass
class Mark:
    blob: Blob
    kind: str


def kind_of(blob: Blob) -> str:
    """Nature d'une marque, d'après sa taille et sa forme."""
    if blob.length < POINT_MAX_MM:
        return POINT
    if blob.hole_fraction >= EMPTY_MIN_HOLE:
        return EMPTY
    elongation = blob.length / max(blob.width, 1e-6)
    thickness = blob.area / blob.length
    thin = elongation >= DASH_MIN_ELONGATION and thickness <= DASH_MAX_THICKNESS_MM
    if thin or elongation >= DASH_ALWAYS_ELONGATION or blob.solidity < FILLED_MIN_SOLIDITY:
        return DASH
    return FILLED


def score(drawing: Drawing, item: int = 9) -> ItemResult:
    codes = ("G", "A", "B", "C", "D", "E", "F")
    if not drawing.blobs:
        return empty_result(item, codes, "aucun tracé dans la zone")
    candidates = [Mark(b, kind_of(b)) for b in drawing.blobs if b.diameter <= MARK_MAX_MM]
    others = [b for b in drawing.blobs if b.diameter > MARK_MAX_MM]
    row, off_row, axis = _row(candidates)
    off_row = [m for m in off_row if m.blob.length >= DUST_MM]
    checks = {code: Checks() for code in codes}
    measures: dict[str, float] = {"nombre_marques": len(candidates)}
    side = np.array([axis[1], -axis[0]]) if axis is not None else np.array([1.0, 0.0])
    if side[0] < 0:
        side = -side
    marks: list = [mk.tache(m.blob.outline, f"{SHORT_NAMES[m.kind]} {fmt(m.blob.diameter, '')}",
                            m.kind == FILLED, side) for m in row + off_row]
    notes: list[str] = []

    def result() -> ItemResult:
        return ItemResult(item, {c: checks[c].criterion(c) for c in codes}, measures, notes,
                          marks)

    all_marks = row + off_row
    large = sum(m.blob.diameter > MOTOR_MAX_DIAMETER_MM for m in all_marks)
    checks["A"].add(bool(all_marks) and large <= len(all_marks) / 2,
                    f"{large} marque(s) sur {len(all_marks)} de plus de 3 mm de diamètre "
                    "(au plus la moitié)")
    dashes = sum(m.kind == DASH for m in all_marks)
    checks["B"].add(bool(all_marks) and dashes == 0,
                    "aucun tiret" if not dashes else f"{dashes} tiret(s)")

    if axis is None:
        reason = f"{len(row)} marque(s) alignée(s) : rangée non reconnue"
        not_recognized(checks, ("G", "C", "D", "E", "F"), reason, notes)
        return result()

    order = np.argsort([m.blob.center @ axis for m in row])
    row = [row[i] for i in order]
    # Angle signé : positif quand la rangée monte de gauche à droite (y vers le bas).
    rise = float(np.degrees(np.arctan2(-axis[1], axis[0])))
    if rise > 90:
        rise -= 180
    elif rise <= -90:
        rise += 180
    kinds = {kind: sum(m.kind == kind for m in row) for kind in (FILLED, POINT, DASH, EMPTY)}
    filled = [m for m in row if m.kind == FILLED]
    not_filled = len(row) - len(filled)
    gaps = [a.blob.distance_to(b.blob) for a, b in zip(row, row[1:])]
    first, last = row[0].blob.center, row[-1].blob.center
    # Longueur de la rangée, du cercle plein le plus à gauche au plus à droite.
    ends = (filled[0], filled[-1]) if len(filled) >= 2 else (row[0], row[-1])
    length = float(np.linalg.norm(ends[1].blob.center - ends[0].blob.center))
    measures.update({"nombre_cercles_pleins": len(filled), "angle_deg": rise,
                     "longueur_mm": length})
    if gaps:
        measures.update({"ecart_min_mm": min(gaps), "ecart_max_mm": max(gaps)})

    low_end = first if first[1] >= last[1] else last
    high_end = last if low_end is first else first
    marks.append(mk.angle(low_end, high_end, low_end + np.array([10.0, 0.0]) * np.sign(
        high_end[0] - low_end[0] or 1), f"{abs(rise):.0f}°"))
    marks.append(mk.cote(ends[0].blob.center, ends[1].blob.center, f"longueur {fmt(length)}",
                         side=-side))
    if gaps:
        for label, index in (("écart min", int(np.argmin(gaps))), ("écart max", int(np.argmax(gaps)))):
            a, b = _closest_points(row[index].blob, row[index + 1].blob)
            marks.append(mk.segment(a, b, f"{label} {fmt(gaps[index])}", side=-side))
            if len(gaps) == 1:
                break

    count_text = ", ".join(f"{n} {kind}(s)" for kind, n in kinds.items() if n)
    lo, hi = ANGLE_RANGE
    general = checks["G"]
    general.add(GENERAL_COUNT[0] <= len(filled) <= GENERAL_COUNT[1] and not_filled == 0,
                f"9 à 11 cercles pleins, sans point, tiret ni cercle vide ({count_text})")
    biggest = max(m.blob.diameter for m in row)
    general.limit(biggest, f"plus grande marque {fmt(biggest)} ≤ 5 mm", high=GENERAL_MAX_DIAMETER_MM)
    general.limit(rise, f"rangée montant de gauche à droite à {rise:.0f}° de l'horizontale "
                  "(entre 30° et 60°)", low=lo, high=hi, unit="deg")

    checks["C"].add(len(row) >= GLOBAL_MIN_MARKS, f"{len(row)} marque(s) alignée(s) (au moins 6)")
    checks["C"].limit(rise, f"rangée montant de gauche à droite ({rise:.0f}°)", low=0.0001,
                      high=90.0, unit="deg")

    checks["D"].limit(rise, f"rangée à {rise:.0f}° de l'horizontale (entre 30° et 60°)",
                      low=lo, high=hi, unit="deg")

    only_filled = not_filled == 0 and not off_row
    filled_text = ("marques toutes en cercles pleins" if only_filled
                   else f"marques qui ne sont pas des cercles pleins ({count_text})")
    checks["E"].add(only_filled, filled_text)
    checks["E"].add(len(filled) == LOCAL_COUNT, f"{len(filled)} cercle(s) plein(s) (dix)")
    checks["F"].add(only_filled, filled_text)
    if gaps:
        checks["E"].limit(min(gaps), f"plus petit écart entre marques voisines {fmt(min(gaps))} "
                          "≥ 2 mm", low=LOCAL_MIN_GAP_MM)
        checks["F"].limit(max(gaps), f"plus grand écart entre marques voisines {fmt(max(gaps))} "
                          "≤ 5 mm", high=LOCAL_MAX_GAP_MM)
    extras = len(others) + len(off_row) + max(0, len(filled) - LOCAL_COUNT)
    checks["F"].add(extras == 0, "aucun autre élément" if not extras
                    else f"{extras} élément(s) en trop")
    checks["F"].limit(length, f"longueur de la rangée {fmt(length)} ≤ 60 mm",
                      high=LOCAL_MAX_LENGTH_MM)
    return result()


def _row(candidates: list[Mark]) -> tuple[list[Mark], list[Mark], np.ndarray | None]:
    """Marques alignées (la plus longue rangée possible), autres marques et
    direction de la rangée (vers la droite)."""
    if len(candidates) < 2:
        return candidates, [], None
    centers = np.array([m.blob.center for m in candidates])
    best = None
    for i, j in combinations(range(len(centers)), 2):
        direction = centers[j] - centers[i]
        if np.linalg.norm(direction) < 1e-6:
            continue
        normal = geo.unit(np.array([-direction[1], direction[0]]))
        near = np.abs((centers - centers[i]) @ normal) <= ROW_DISTANCE_MM
        if best is None or near.sum() > best.sum():
            best = near
    if best is None:
        return candidates, [], None
    _, axis = geo.principal_axis(centers[best])
    if axis[0] < 0 or (axis[0] == 0 and axis[1] > 0):
        axis = -axis
    row = [m for m, keep in zip(candidates, best) if keep]
    off_row = [m for m, keep in zip(candidates, best) if not keep]
    return row, off_row, axis


def _closest_points(a: Blob, b: Blob) -> tuple[np.ndarray, np.ndarray]:
    diff = a.outline[:, None, :] - b.outline[None, :, :]
    i, j = np.unravel_index(int(np.argmin((diff ** 2).sum(-1))), diff.shape[:2])
    return a.outline[i], b.outline[j]
