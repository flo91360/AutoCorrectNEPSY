"""Item 6 : « V ».

Seuils repris du manuel NEPSY-II (Copie de figures), reformulés.
"""

from __future__ import annotations

import numpy as np

from .. import geometry as geo
from ..strokes import Drawing
from .base import Checks, ItemResult, Scoring, fmt, fmt_ratio, manual_thresholds
from . import marks as mk
from .shapes import (check_direction_changes, check_lines, end_at, extra_elements,
                     intersection, review_notes)

# Seuils du manuel, reformulés (liste : autocorrect-nepsy seuils).
threshold = manual_thresholds(__name__)
JUNCTION_MM = threshold(2.0, "GAE", "intervalle ou dépassement au sommet, au plus")
GENERAL_SLOPE = (threshold(45.0, "G", "angle de chaque ligne avec l'horizontale, au moins", "deg"),
                 threshold(75.0, "G", "angle de chaque ligne avec l'horizontale, au plus", "deg"))
GENERAL_MAX_RATIO = threshold(2.0, "G", "rapport de la plus longue à la plus courte ligne, au "
                              "plus", "ratio")
STRAIGHT_BAND_MM = threshold(4.0, "A", "largeur de la barre grisée où tient chaque ligne")
MAX_DIRECTION_CHANGES = threshold(3, "B", "changements de direction par ligne, au plus", "nombre")
GLOBAL_MAX_SLOPE = threshold(75.0, "C", "angle de chaque ligne avec l'horizontale, au plus", "deg")
APEX_RANGE = (threshold(40.0, "D", "angle au sommet, au moins", "deg"),
              threshold(80.0, "D", "angle au sommet, au plus", "deg"))
LOCAL_MAX_LENGTH_MM = threshold(80.0, "F", "longueur de chaque ligne, au plus")
LOCAL_MAX_RATIO = threshold(1.3, "F", "rapport de la plus longue à la plus courte ligne, au plus",
                            "ratio")


def score(drawing: Drawing, item: int = 6) -> ItemResult:
    scoring = Scoring(item, "GABCDEF")
    if drawing.is_empty:
        return scoring.empty()
    lines = drawing.significant_lines()
    scoring.measures["nombre_lignes"] = len(lines)
    scoring.notes += review_notes(lines)
    check_lines(scoring["A"], lines, STRAIGHT_BAND_MM)
    check_direction_changes(scoring["B"], lines, MAX_DIRECTION_CHANGES)

    scoring.marks += [mk.bande(line) for line in lines]

    apex = intersection(lines[0], lines[1]) if len(lines) >= 2 else None
    if apex is None:
        reason = "il faut deux lignes qui convergent"
        scoring.not_recognized(("G", "A", "C", "D", "E", "F"), reason)
        return scoring.result()

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
    scoring.marks += [mk.line_length(left), mk.line_length(right),
                      mk.angle(apex, far[0], far[1], f"{apex_angle:.0f}°")]
    for end, slope in zip(far, slopes):
        toward_apex = np.array([np.sign(apex[0] - end[0]) or 1.0, 0.0])
        scoring.marks.append(mk.angle(end, end + toward_apex * 12, apex,
                                      f"{slope:.0f}° / horizontale"))
    if gap >= 0.5 or overshoot >= 0.5:
        scoring.marks.append(mk.point(apex, f"intervalle {fmt(gap)}, dépassement {fmt(overshoot)}"))
    scoring.measures.update({"ligne_gauche_mm": left.length, "ligne_droite_mm": right.length,
                             "intervalle_mm": gap, "depassement_mm": overshoot,
                             "angle_sommet_deg": apex_angle, "pente_gauche_deg": slopes[0],
                             "pente_droite_deg": slopes[1], "rapport_longueurs": ratio})

    def junction_checks(checks_: Checks) -> None:
        checks_.limit(gap, f"intervalle au sommet {fmt(gap)} ≤ {JUNCTION_MM.text}",
                      high=JUNCTION_MM)
        checks_.limit(overshoot, f"dépassement au sommet {fmt(overshoot)} ≤ {JUNCTION_MM.text}",
                      high=JUNCTION_MM)

    lo, hi = GENERAL_SLOPE
    general = scoring["G"]
    general.add(two_lines, f"seulement deux lignes convergent ({len(lines)} trouvée(s))")
    junction_checks(general)
    for name, slope in zip(("gauche", "droite"), slopes):
        general.limit(slope, f"ligne {name} à {slope:.0f}° de l'horizontale "
                      f"({lo.text} à {hi.text})",
                      low=lo, high=hi, unit="deg")
    general.limit(ratio, f"rapport des longueurs {fmt_ratio(ratio)} ≤ {GENERAL_MAX_RATIO.text}",
                  high=GENERAL_MAX_RATIO, unit="ratio")

    junction_checks(scoring["A"])

    scoring["C"].add(opens_upward, "la figure forme un « V » (sommet en bas)")
    for name, slope in zip(("gauche", "droite"), slopes):
        scoring["C"].limit(slope, f"ligne {name} à {slope:.0f}° de l'horizontale "
                           f"(≤ {GLOBAL_MAX_SLOPE.text})",
                           high=GLOBAL_MAX_SLOPE, unit="deg")

    lo, hi = APEX_RANGE
    scoring["D"].limit(apex_angle, f"angle au sommet {apex_angle:.0f}° (entre {lo.text} et {hi.text})",
                       low=lo, high=hi, unit="deg")

    scoring["E"].add(two_lines, f"seulement deux lignes ({len(lines)} trouvée(s))")
    scoring["E"].limit(gap, f"les deux lignes convergent (intervalle {fmt(gap)})", high=JUNCTION_MM)

    extras = extra_elements(drawing, [left, right])
    scoring["F"].add(not extras, "aucun autre élément" if not extras
                     else f"{len(extras)} élément(s) en trop")
    scoring["F"].limit(max(lengths), f"longueur des lignes {fmt(max(lengths))} ≤ "
                       f"{LOCAL_MAX_LENGTH_MM.text}", high=LOCAL_MAX_LENGTH_MM)
    scoring["F"].limit(ratio, f"rapport des longueurs {fmt_ratio(ratio)} ≤ {LOCAL_MAX_RATIO.text}",
                       high=LOCAL_MAX_RATIO, unit="ratio")

    return scoring.result()
