"""Item 6 : « V ».

Seuils repris du manuel NEPSY-II (Copie de figures), reformulés.
"""

from __future__ import annotations

import numpy as np

from .. import geometry as geo
from ..strokes import Drawing
from .base import Checks, ItemResult, empty_result, fmt, fmt_ratio
from . import marks as mk
from .shapes import (check_direction_changes, check_lines, end_at, extra_elements,
                     intersection, review_notes)

JUNCTION_MM = 2.0  # intervalle / dépassement toléré au point de convergence
GENERAL_SLOPE = (45.0, 75.0)  # Général : angle de chaque ligne avec l'horizontale
GENERAL_MAX_RATIO = 2.0
STRAIGHT_BAND_MM = 4.0  # Motricité A
MAX_DIRECTION_CHANGES = 3  # Motricité B
GLOBAL_MAX_SLOPE = 75.0  # Global C
APEX_RANGE = (40.0, 80.0)  # Global D : angle au sommet
LOCAL_MAX_LENGTH_MM = 80.0  # Local F
LOCAL_MAX_RATIO = 1.3  # Local F


def score(drawing: Drawing, item: int = 6) -> ItemResult:
    codes = ("G", "A", "B", "C", "D", "E", "F")
    if drawing.is_empty:
        return empty_result(item, codes, "aucun tracé dans la zone")
    lines = drawing.significant_lines()
    checks = {code: Checks() for code in codes}
    measures: dict[str, float] = {"nombre_lignes": len(lines)}
    notes = review_notes(lines)
    check_lines(checks["A"], lines, STRAIGHT_BAND_MM)
    check_direction_changes(checks["B"], lines, MAX_DIRECTION_CHANGES)

    marks: list = [mk.bande(line) for line in lines]

    def result() -> ItemResult:
        return ItemResult(item, {c: checks[c].criterion(c) for c in codes}, measures, notes,
                          marks)

    apex = intersection(lines[0], lines[1]) if len(lines) >= 2 else None
    if apex is None:
        reason = "il faut deux lignes qui convergent"
        for code in ("G", "A", "C", "D", "E", "F"):
            checks[code].fail(reason)
        return result()

    left, right = sorted(lines[:2], key=lambda l: l.center[0])
    ends = [end_at(line, apex) for line in (left, right)]
    gap = max(e.gap for e in ends)
    overshoot = max(e.overshoot for e in ends)
    far = [max(line.ends, key=lambda p: np.linalg.norm(p - apex)) for line in (left, right)]
    apex_angle = geo.angle_between(far[0] - apex, far[1] - apex)
    slopes = [left.angle_to_horizontal(), right.angle_to_horizontal()]
    opens_upward = all(p[1] < apex[1] for p in far)
    lengths = [left.length, right.length]
    ratio = max(lengths) / max(min(lengths), 1e-6)
    two_lines = len(lines) == 2
    marks += [mk.line_length(left), mk.line_length(right),
              mk.angle(apex, far[0], far[1], f"{apex_angle:.0f}°")]
    for end, slope in zip(far, slopes):
        toward_apex = np.array([np.sign(apex[0] - end[0]) or 1.0, 0.0])
        marks.append(mk.angle(end, end + toward_apex * 12, apex, f"{slope:.0f}° / horizontale"))
    if gap >= 0.5 or overshoot >= 0.5:
        marks.append(mk.point(apex, f"intervalle {fmt(gap)}, dépassement {fmt(overshoot)}"))
    measures.update({"ligne_gauche_mm": left.length, "ligne_droite_mm": right.length,
                     "intervalle_mm": gap, "depassement_mm": overshoot,
                     "angle_sommet_deg": apex_angle, "pente_gauche_deg": slopes[0],
                     "pente_droite_deg": slopes[1], "rapport_longueurs": ratio})

    def junction_checks(checks_: Checks) -> None:
        checks_.limit(gap, f"intervalle au sommet {fmt(gap)} ≤ 2 mm", high=JUNCTION_MM)
        checks_.limit(overshoot, f"dépassement au sommet {fmt(overshoot)} ≤ 2 mm", high=JUNCTION_MM)

    lo, hi = GENERAL_SLOPE
    general = checks["G"]
    general.add(two_lines, f"seulement deux lignes convergent ({len(lines)} trouvée(s))")
    junction_checks(general)
    for name, slope in zip(("gauche", "droite"), slopes):
        general.limit(slope, f"ligne {name} à {slope:.0f}° de l'horizontale (45° à 75°)",
                      low=lo, high=hi, unit="deg")
    general.limit(ratio, f"rapport des longueurs {fmt_ratio(ratio)} ≤ 2:1",
                  high=GENERAL_MAX_RATIO, unit="ratio")

    junction_checks(checks["A"])

    checks["C"].add(opens_upward, "la figure forme un « V » (sommet en bas)")
    for name, slope in zip(("gauche", "droite"), slopes):
        checks["C"].limit(slope, f"ligne {name} à {slope:.0f}° de l'horizontale (≤ 75°)",
                          high=GLOBAL_MAX_SLOPE, unit="deg")

    lo, hi = APEX_RANGE
    checks["D"].limit(apex_angle, f"angle au sommet {apex_angle:.0f}° (entre 40° et 80°)",
                      low=lo, high=hi, unit="deg")

    checks["E"].add(two_lines, f"seulement deux lignes ({len(lines)} trouvée(s))")
    checks["E"].limit(gap, f"les deux lignes convergent (intervalle {fmt(gap)})", high=JUNCTION_MM)

    extras = extra_elements(drawing, [left, right])
    checks["F"].add(not extras, "aucun autre élément" if not extras
                    else f"{len(extras)} élément(s) en trop")
    checks["F"].limit(max(lengths), f"longueur des lignes {fmt(max(lengths))} ≤ 80 mm",
                      high=LOCAL_MAX_LENGTH_MM)
    checks["F"].limit(ratio, f"rapport des longueurs {fmt_ratio(ratio)} ≤ 1,3:1",
                      high=LOCAL_MAX_RATIO, unit="ratio")

    return result()
