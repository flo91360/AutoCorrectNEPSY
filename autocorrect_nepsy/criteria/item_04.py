"""Item 4 : carré.

Seuils repris du manuel NEPSY-II (Copie de figures), reformulés.
"""

from __future__ import annotations

import numpy as np

from .. import geometry as geo
from ..strokes import Drawing
from .base import Checks, ItemResult, empty_result, fmt, fmt_ratio
from . import marks as mk
from .shapes import check_lines, end_at, extra_elements, intersection, review_notes

GENERAL_MAX_RATIO = 2.0  # rapport plus long / plus court côté
MAX_INTERRUPTIONS = 3  # Motricité A, par ligne
STRAIGHT_BAND_MM = 4.0  # Motricité A : barre grisée de 4 mm
OVERSHOOT_MM = 5.0  # Motricité B : moins de deux dépassements de plus de 5 mm
HORIZONTAL_SIDES_DEG = 30.0  # Global C : côtés haut et bas
CORNER_RANGE = (60.0, 120.0)  # Global D : angles des coins
LOCAL_MAX_SIDE_MM = 70.0  # Local F : plus long côté
LOCAL_MAX_RATIO = 1.3  # Local F


def score(drawing: Drawing, item: int = 4) -> ItemResult:
    codes = ("G", "A", "B", "C", "D", "E", "F")
    if drawing.is_empty:
        return empty_result(item, codes, "aucun tracé dans la zone")
    lines = drawing.significant_lines()
    horizontals = [l for l in lines if l.angle_to_horizontal() <= 45]
    verticals = [l for l in lines if l.angle_to_horizontal() > 45]
    checks = {code: Checks() for code in codes}
    measures: dict[str, float] = {"nombre_lignes": len(lines)}
    notes = review_notes(lines)

    check_lines(checks["A"], lines, STRAIGHT_BAND_MM, MAX_INTERRUPTIONS)
    checks["E"].add(len(lines) == 4, f"seulement quatre lignes ({len(lines)} trouvée(s))")

    marks: list = [mk.bande(line) for line in lines]

    def result() -> ItemResult:
        return ItemResult(item, {c: checks[c].criterion(c) for c in codes}, measures, notes,
                          marks)

    if len(horizontals) < 2 or len(verticals) < 2:
        reason = (f"figure à quatre côtés non reconnue ({len(horizontals)} côté(s) "
                  f"horizontal(aux), {len(verticals)} vertical(aux))")
        for code in ("G", "B", "C", "D", "F"):
            checks[code].fail(reason)
        return result()

    top, bottom = sorted(horizontals[:2], key=lambda l: l.center[1])
    left, right = sorted(verticals[:2], key=lambda l: l.center[0])
    corners = {
        "haut-gauche": (top, left), "haut-droit": (top, right),
        "bas-droit": (bottom, right), "bas-gauche": (bottom, left),
    }
    points = {name: intersection(a, b) for name, (a, b) in corners.items()}
    if any(p is None for p in points.values()):
        for code in ("G", "B", "C", "D", "F"):
            checks[code].fail("côtés parallèles : coins introuvables")
        return result()

    tl, tr, br, bl = (points[n] for n in corners)
    sides = {"haut": np.linalg.norm(tr - tl), "bas": np.linalg.norm(br - bl),
             "gauche": np.linalg.norm(bl - tl), "droit": np.linalg.norm(br - tr)}
    angles = {
        "haut-gauche": geo.angle_between(tr - tl, bl - tl),
        "haut-droit": geo.angle_between(tl - tr, br - tr),
        "bas-droit": geo.angle_between(tr - br, bl - br),
        "bas-gauche": geo.angle_between(br - bl, tl - bl),
    }
    overshoots = [end_at(line, points[name]).overshoot
                  for name, pair in corners.items() for line in pair]
    big_overshoots = sum(o > OVERSHOOT_MM for o in overshoots)
    near_overshoots = any(abs(o - OVERSHOOT_MM) <= 0.5 for o in overshoots)
    ratio = max(sides.values()) / max(min(sides.values()), 1e-6)
    longest = max(sides.values())
    for (a, b), side in zip(((tl, tr), (br, bl), (bl, tl), (tr, br)), sides):
        marks.append(mk.cote(a, b, fmt(sides[side])))
    for name, (vertex, p1, p2) in {"haut-gauche": (tl, tr, bl), "haut-droit": (tr, tl, br),
                                    "bas-droit": (br, tr, bl), "bas-gauche": (bl, br, tl)}.items():
        marks.append(mk.angle(vertex, p1, p2, f"{angles[name]:.0f}°"))
    measures.update({f"cote_{k}_mm": float(v) for k, v in sides.items()})
    measures.update({f"angle_{k}_deg": v for k, v in angles.items()})
    measures["rapport_cotes"] = ratio
    extras = extra_elements(drawing, [top, bottom, left, right])

    checks["G"].add(len(lines) == 4, f"quatre côtés nettement définis ({len(lines)} ligne(s))")
    checks["G"].limit(ratio, f"rapport des côtés {fmt_ratio(ratio)} ≤ 2:1",
                      high=GENERAL_MAX_RATIO, unit="ratio")

    checks["B"].add(big_overshoots < 2,
                    f"{big_overshoots} dépassement(s) de plus de 5 mm aux coins (moins de 2)",
                    near=near_overshoots)

    checks["C"].add(True, "forme carrée ou rectangulaire à quatre coins")
    for name, line in (("haut", top), ("bas", bottom)):
        angle = line.angle_to_horizontal()
        checks["C"].limit(angle, f"côté {name} à {angle:.0f}° de l'horizontale (≤ 30°)",
                          high=HORIZONTAL_SIDES_DEG, unit="deg")

    lo, hi = CORNER_RANGE
    for name, angle in angles.items():
        checks["D"].limit(angle, f"coin {name} : {angle:.0f}° (entre 60° et 120°)",
                          low=lo, high=hi, unit="deg")

    checks["F"].add(not extras, "aucun autre élément" if not extras
                    else f"{len(extras)} élément(s) en trop")
    checks["F"].limit(longest, f"plus long côté {fmt(longest)} ≤ 70 mm", high=LOCAL_MAX_SIDE_MM)
    checks["F"].limit(ratio, f"rapport des côtés {fmt_ratio(ratio)} ≤ 1,3:1",
                      high=LOCAL_MAX_RATIO, unit="ratio")

    return result()
