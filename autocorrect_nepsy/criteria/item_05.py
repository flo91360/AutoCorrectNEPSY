"""Item 5 : trait vertical avec un trait horizontal partant vers la droite.

Seuils repris du manuel NEPSY-II (Copie de figures), reformulés.
"""

from __future__ import annotations

from ..strokes import Drawing
from .base import Checks, ItemResult, empty_result, fmt, fmt_ratio
from . import marks as mk
from .shapes import (check_lines, end_at, extra_elements, intersection, outside,
                     review_notes)

JUNCTION_MM = 2.0  # intervalle / dépassement toléré à l'intersection
GENERAL_MAX_OVERSHOOT = 0.25  # Général : dépassement ≤ 1/4 de la ligne horizontale
GENERAL_AXIS_DEG = 20.0  # Général : écart à l'axe de chaque ligne
RELATIVE_AXIS_DEG = 45.0  # Global C : « relativement » vertical / horizontal
MAX_INTERRUPTIONS = 3  # Motricité A
STRAIGHT_BAND_MM = 4.0  # Motricité A
LENGTH_RATIO = (1.5, 3.0)  # Local F : verticale / horizontale


def score(drawing: Drawing, item: int = 5) -> ItemResult:
    codes = ("G", "A", "B", "C", "D", "E", "F")
    if drawing.is_empty:
        return empty_result(item, codes, "aucun tracé dans la zone")
    lines = drawing.significant_lines()
    checks = {code: Checks() for code in codes}
    measures: dict[str, float] = {"nombre_lignes": len(lines)}
    notes = review_notes(lines)
    check_lines(checks["A"], lines, STRAIGHT_BAND_MM, MAX_INTERRUPTIONS)

    marks: list = [mk.bande(line, at="bout") for line in lines]

    def result() -> ItemResult:
        return ItemResult(item, {c: checks[c].criterion(c) for c in codes}, measures, notes,
                          marks)

    verticals = [l for l in lines if l.angle_to_vertical() < 45]
    horizontals = [l for l in lines if l.angle_to_horizontal() <= 45]
    junction = intersection(verticals[0], horizontals[0]) if verticals and horizontals else None
    if junction is None:
        reason = "il faut une ligne verticale et une ligne horizontale qui se rejoignent"
        for code in ("G", "B", "C", "D", "E", "F"):
            checks[code].fail(reason)
        return result()

    vertical, horizontal = verticals[0], horizontals[0]
    h_end = end_at(horizontal, junction)
    gap = max(h_end.gap, outside(vertical, junction))
    overshoot = h_end.overshoot
    position = (vertical.position(junction) - vertical.t0) / max(vertical.length, 1e-6)
    if vertical.ends[0][1] > vertical.ends[1][1]:
        position = 1 - position  # position comptée depuis le haut
    far_end = max(horizontal.ends, key=lambda p: abs(p[0] - junction[0]))
    goes_right = far_end[0] > junction[0]
    ratio = vertical.length / max(horizontal.length, 1e-6)
    two_lines = len(lines) == 2
    max_overshoot = GENERAL_MAX_OVERSHOOT * horizontal.length
    junction_text = f"jonction à {position:.0%} de la hauteur"
    if gap >= 0.5:
        junction_text += f", intervalle {fmt(gap)}"
    if overshoot >= 0.5:
        junction_text += f", dépassement {fmt(overshoot)}"
    marks += [mk.line_length(vertical), mk.line_length(horizontal), mk.point(junction, junction_text)]
    measures.update({"verticale_mm": vertical.length, "horizontale_mm": horizontal.length,
                     "intervalle_mm": gap, "depassement_mm": overshoot,
                     "position_intersection": position, "rapport_longueurs": ratio})
    third = f"intersection à {position:.0%} de la hauteur de la verticale (tiers central)"

    general = checks["G"]
    general.add(two_lines, f"intersection de seulement deux lignes ({len(lines)} trouvée(s))")
    general.limit(gap, f"intervalle à l'intersection {fmt(gap)} ≤ 2 mm", high=JUNCTION_MM)
    general.limit(overshoot, f"dépassement {fmt(overshoot)} ≤ quart de l'horizontale "
                  f"({fmt(max_overshoot)})", high=max_overshoot)
    general.limit(vertical.angle_to_vertical(),
                  f"verticale à {vertical.angle_to_vertical():.0f}° de l'axe (≤ 20°)",
                  high=GENERAL_AXIS_DEG, unit="deg")
    general.limit(horizontal.angle_to_horizontal(),
                  f"horizontale à {horizontal.angle_to_horizontal():.0f}° de l'axe (≤ 20°)",
                  high=GENERAL_AXIS_DEG, unit="deg")
    general.limit(position, third, low=1 / 3, high=2 / 3, unit="part")

    checks["B"].limit(gap, f"intervalle à l'intersection {fmt(gap)} ≤ 2 mm", high=JUNCTION_MM)
    checks["B"].limit(overshoot, f"dépassement à l'intersection {fmt(overshoot)} ≤ 2 mm",
                      high=JUNCTION_MM)

    checks["C"].limit(vertical.angle_to_vertical(), "ligne de gauche relativement verticale "
                      f"({vertical.angle_to_vertical():.0f}°)", high=RELATIVE_AXIS_DEG, unit="deg")
    checks["C"].limit(horizontal.angle_to_horizontal(), "ligne de droite relativement horizontale "
                      f"({horizontal.angle_to_horizontal():.0f}°)", high=RELATIVE_AXIS_DEG, unit="deg")
    checks["C"].add(goes_right, "la ligne horizontale part vers la droite")

    checks["D"].limit(position, third, low=1 / 3, high=2 / 3, unit="part")

    checks["E"].add(two_lines, f"seulement deux lignes ({len(lines)} trouvée(s))")
    checks["E"].limit(gap, f"les deux lignes se rejoignent (intervalle {fmt(gap)})",
                      high=JUNCTION_MM)

    extras = extra_elements(drawing, [vertical, horizontal])
    checks["F"].add(not extras, "aucun autre élément" if not extras
                    else f"{len(extras)} élément(s) en trop")
    lo, hi = LENGTH_RATIO
    checks["F"].limit(ratio, f"rapport verticale / horizontale {fmt_ratio(ratio)} "
                      "entre 1,5:1 et 3:1", low=lo, high=hi, unit="ratio")

    return result()
