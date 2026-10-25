"""Item 7 : deux traits verticaux coupés par un trait horizontal.

Seuils repris du manuel NEPSY-II (Copie de figures), reformulés.
"""

from __future__ import annotations

import numpy as np

from .. import geometry as geo
from ..strokes import Drawing, StraightLine
from .base import Checks, ItemResult, empty_result, fmt, fmt_ratio
from . import marks as mk
from .shapes import (check_direction_changes, check_lines, extra_elements, intersection,
                     outside, review_notes)

AXIS_DEG = 20.0  # Général et Global C : écart à l'axe
CROSSING_TOLERANCE_MM = 1.0  # l'intersection doit tomber sur les deux tracés
GENERAL_MAX_RATIO = 2.0
MAX_INTERRUPTIONS = 2  # Motricité A
STRAIGHT_BAND_MM = 3.0  # Motricité A
MAX_DIRECTION_CHANGES = 3  # Motricité B
CROSSING_ANGLES = (60.0, 120.0)  # Global C
GLOBAL_MAX_PAIR_RATIO = 1.2  # Global D
LOCAL_MIN_HORIZONTAL_MM = 20.0  # Local E
LOCAL_MAX_RATIO = 2.0  # Local F


def _above_below(line: StraightLine, point) -> tuple[float, float]:
    """Longueurs du trait vertical au-dessus et au-dessous d'un point."""
    t = line.position(point)
    top_is_t0 = line.ends[0][1] < line.ends[1][1]
    above, below = (t - line.t0, line.t1 - t) if top_is_t0 else (line.t1 - t, t - line.t0)
    return max(above, 0.0), max(below, 0.0)


def score(drawing: Drawing, item: int = 7) -> ItemResult:
    codes = ("G", "A", "B", "C", "D", "E", "F")
    if drawing.is_empty:
        return empty_result(item, codes, "aucun tracé dans la zone")
    lines = drawing.significant_lines()
    checks = {code: Checks() for code in codes}
    measures: dict[str, float] = {"nombre_lignes": len(lines)}
    notes = review_notes(lines)
    check_lines(checks["A"], lines, STRAIGHT_BAND_MM, MAX_INTERRUPTIONS)
    check_direction_changes(checks["B"], lines, MAX_DIRECTION_CHANGES)

    marks: list = [mk.bande(line, at="bout") for line in lines]

    def result() -> ItemResult:
        return ItemResult(item, {c: checks[c].criterion(c) for c in codes}, measures, notes,
                          marks)

    horizontals = [l for l in lines if l.angle_to_horizontal() <= 45]
    verticals = [l for l in lines if l.angle_to_horizontal() > 45]
    if horizontals:
        checks["E"].limit(horizontals[0].length,
                          f"ligne horizontale entière {fmt(horizontals[0].length)} ≥ 20 mm",
                          low=LOCAL_MIN_HORIZONTAL_MM)
    else:
        checks["E"].fail("aucune ligne horizontale")
    if not horizontals or len(verticals) < 2:
        reason = (f"figure non reconnue : {len(horizontals)} ligne(s) horizontale(s), "
                  f"{len(verticals)} verticale(s) (il en faut 1 et 2)")
        for code in ("G", "C", "D", "F"):
            checks[code].fail(reason)
        return result()

    horizontal = horizontals[0]
    v_left, v_right = sorted(verticals[:2], key=lambda l: l.center[0])
    crossings = [intersection(horizontal, v) for v in (v_left, v_right)]
    if any(p is None for p in crossings):
        for code in ("G", "C", "D", "F"):
            checks[code].fail("lignes parallèles : pas d'intersection")
        return result()

    crosses = all(outside(horizontal, p) <= CROSSING_TOLERANCE_MM
                  and outside(v, p) <= CROSSING_TOLERANCE_MM
                  for p, v in zip(crossings, (v_left, v_right)))
    t_cross = sorted(horizontal.position(p) for p in crossings)
    seg_left = max(t_cross[0] - horizontal.t0, 0.0)
    seg_center = t_cross[1] - t_cross[0]
    seg_right = max(horizontal.t1 - t_cross[1], 0.0)
    (up_l, down_l), (up_r, down_r) = (_above_below(v, p) for v, p in zip((v_left, v_right), crossings))
    ups, downs = [up_l, up_r], [down_l, down_r]
    shortest = min(ups + downs)
    opposite = max(downs) if shortest in ups else max(ups)
    pair_ratio = opposite / max(shortest, 1e-6)
    outer_ratio = max(seg_left, seg_right) / max(min(seg_left, seg_right), 1e-6)
    side = min(seg_left, seg_right)
    center_ratio = seg_center / max(side, 1e-6)
    crossing_angles = [geo.angle_between(horizontal.direction, v.direction) for v in (v_left, v_right)]
    three_lines = len(lines) == 3
    on_h = [horizontal.center + t * horizontal.direction
            for t in (horizontal.t0, t_cross[0], t_cross[1], horizontal.t1)]
    for (a, b), length in zip(zip(on_h, on_h[1:]), (seg_left, seg_center, seg_right)):
        marks.append(mk.cote(a, b, fmt(length), side=(0.0, 1.0)))
    for v, p, side in ((v_left, crossings[0], (-1.0, 0.0)), (v_right, crossings[1], (1.0, 0.0))):
        top, bottom = sorted(v.ends, key=lambda q: q[1])
        up, down = _above_below(v, p)
        marks += [mk.cote(top, p, fmt(up), side=side), mk.cote(p, bottom, fmt(down), side=side)]
    for v, p, value in zip((v_left, v_right), crossings, crossing_angles):
        top = min(v.ends, key=lambda q: q[1])
        marks.append(mk.angle(p, p + np.asarray(horizontal.direction) * 8, top, f"{value:.0f}°"))
    measures.update({"horizontale_mm": horizontal.length, "segment_gauche_mm": seg_left,
                     "segment_central_mm": seg_center, "segment_droit_mm": seg_right,
                     "rapport_segments_verticaux": pair_ratio,
                     "rapport_segments_exterieurs": outer_ratio})

    def axis_checks(checks_: Checks) -> None:
        angle = horizontal.angle_to_horizontal()
        checks_.limit(angle, f"horizontale à {angle:.0f}° de l'axe (≤ 20°)",
                      high=AXIS_DEG, unit="deg")
        for name, v in (("gauche", v_left), ("droite", v_right)):
            checks_.limit(v.angle_to_vertical(),
                          f"verticale {name} à {v.angle_to_vertical():.0f}° de l'axe (≤ 20°)",
                          high=AXIS_DEG, unit="deg")

    general = checks["G"]
    general.add(three_lines and crosses,
                f"une seule horizontale coupe deux verticales ({len(lines)} ligne(s))")
    axis_checks(general)
    general.limit(outer_ratio, f"segments horizontaux extérieurs : rapport "
                  f"{fmt_ratio(outer_ratio)} ≤ 2:1", high=GENERAL_MAX_RATIO, unit="ratio")
    general.limit(pair_ratio, f"segments verticaux opposés : rapport {fmt_ratio(pair_ratio)} ≤ 2:1",
                  high=GENERAL_MAX_RATIO, unit="ratio")

    checks["C"].add(crosses, "la figure forme un « H » (les lignes se coupent)")
    axis_checks(checks["C"])
    lo, hi = CROSSING_ANGLES
    for name, angle in zip(("gauche", "droite"), crossing_angles):
        checks["C"].limit(angle, f"angles au croisement {name} : {angle:.0f}° (60° à 120°)",
                          low=lo, high=hi, unit="deg")

    checks["D"].limit(pair_ratio, f"segments verticaux opposés : rapport "
                      f"{fmt_ratio(pair_ratio)} ≤ 1,2:1", high=GLOBAL_MAX_PAIR_RATIO, unit="ratio")

    extras = extra_elements(drawing, [horizontal, v_left, v_right])
    checks["F"].add(not extras, "aucun autre élément" if not extras
                    else f"{len(extras)} élément(s) en trop")
    checks["F"].limit(seg_center, f"segment central {fmt(seg_center)} ≥ segments gauche "
                      f"({fmt(seg_left)}) et droit ({fmt(seg_right)})",
                      low=max(seg_left, seg_right))
    checks["F"].limit(center_ratio, f"rapport segment central / latéraux "
                      f"{fmt_ratio(center_ratio)} ≤ 2:1", high=LOCAL_MAX_RATIO, unit="ratio")

    return result()
