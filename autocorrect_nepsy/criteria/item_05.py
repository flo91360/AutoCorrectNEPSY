"""Item 5 : trait vertical avec un trait horizontal partant vers la droite.

Seuils repris du manuel NEPSY-II (Copie de figures), reformulés.
"""

from __future__ import annotations

from ..strokes import Drawing
from .base import ItemResult, Scoring, fmt, fmt_ratio, manual_thresholds
from . import marks as mk
from .shapes import (check_lines, end_at, extra_elements, intersection, outside,
                     review_notes)

# Seuils du manuel, reformulés (liste : autocorrect-nepsy seuils).
threshold = manual_thresholds(__name__)
JUNCTION_MM = threshold(2.0, "GBE", "intervalle ou dépassement à l'intersection, au plus")
GENERAL_MAX_OVERSHOOT = threshold(0.25, "G", "dépassement à l'intersection, en part de la ligne "
                                  "horizontale, au plus", "part")
GENERAL_AXIS_DEG = threshold(20.0, "G", "écart de chaque ligne à son axe, au plus", "deg")
CENTRAL_THIRD = (threshold(1 / 3, "GD", "position de l'intersection sur la verticale, depuis "
                           "le haut, au moins (tiers central)", "part"),
                 threshold(2 / 3, "GD", "position de l'intersection sur la verticale, depuis "
                           "le haut, au plus (tiers central)", "part"))
MAX_INTERRUPTIONS = threshold(3, "A", "interruptions par ligne, au plus", "nombre")
STRAIGHT_BAND_MM = threshold(4.0, "A", "largeur de la barre grisée où tient chaque ligne")
LENGTH_RATIO = (threshold(1.5, "F", "rapport de la verticale à l'horizontale, au moins", "ratio"),
                threshold(3.0, "F", "rapport de la verticale à l'horizontale, au plus", "ratio"))
# Réglages de l'outil (reconnaissance des figures, tolérances de mesure).
# Global C : « relativement » vertical / horizontal, interprété par l'outil.
RELATIVE_AXIS_DEG = 45.0


def score(drawing: Drawing, item: int = 5) -> ItemResult:
    scoring = Scoring(item, "GABCDEF")
    if drawing.is_empty:
        return scoring.empty()
    lines = drawing.significant_lines()
    scoring.measures["nombre_lignes"] = len(lines)
    scoring.notes += review_notes(lines)
    check_lines(scoring["A"], lines, STRAIGHT_BAND_MM, MAX_INTERRUPTIONS)

    scoring.marks += [mk.bande(line, at="bout") for line in lines]

    verticals = [l for l in lines if l.angle_to_vertical() < 45]
    horizontals = [l for l in lines if l.angle_to_horizontal() <= 45]
    junction = intersection(verticals[0], horizontals[0]) if verticals and horizontals else None
    if junction is None:
        reason = "il faut une ligne verticale et une ligne horizontale qui se rejoignent"
        scoring.not_recognized(("G", "B", "C", "D", "E", "F"), reason)
        return scoring.result()

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
    scoring.marks += [mk.line_length(vertical), mk.line_length(horizontal),
                      mk.point(junction, junction_text)]
    scoring.measures.update({"verticale_mm": vertical.length, "horizontale_mm": horizontal.length,
                             "intervalle_mm": gap, "depassement_mm": overshoot,
                             "position_intersection": position, "rapport_longueurs": ratio})
    third = f"intersection à {position:.0%} de la hauteur de la verticale (tiers central)"

    general = scoring["G"]
    general.add(two_lines, f"intersection de seulement deux lignes ({len(lines)} trouvée(s))")
    general.limit(gap, f"intervalle à l'intersection {fmt(gap)} ≤ {JUNCTION_MM.text}",
                  high=JUNCTION_MM)
    general.limit(overshoot, f"dépassement {fmt(overshoot)} ≤ quart de l'horizontale "
                  f"({fmt(max_overshoot)})", high=max_overshoot)
    general.limit(vertical.angle_to_vertical(),
                  f"verticale à {vertical.angle_to_vertical():.0f}° de l'axe "
                  f"(≤ {GENERAL_AXIS_DEG.text})",
                  high=GENERAL_AXIS_DEG, unit="deg")
    general.limit(horizontal.angle_to_horizontal(),
                  f"horizontale à {horizontal.angle_to_horizontal():.0f}° de l'axe "
                  f"(≤ {GENERAL_AXIS_DEG.text})",
                  high=GENERAL_AXIS_DEG, unit="deg")
    first, last = CENTRAL_THIRD
    general.limit(position, third, low=first, high=last, unit="part")

    scoring["B"].limit(gap, f"intervalle à l'intersection {fmt(gap)} ≤ {JUNCTION_MM.text}",
                       high=JUNCTION_MM)
    scoring["B"].limit(overshoot, f"dépassement à l'intersection {fmt(overshoot)} ≤ "
                       f"{JUNCTION_MM.text}", high=JUNCTION_MM)

    scoring["C"].limit(vertical.angle_to_vertical(), "ligne de gauche relativement verticale "
                       f"({vertical.angle_to_vertical():.0f}°)", high=RELATIVE_AXIS_DEG, unit="deg")
    scoring["C"].limit(horizontal.angle_to_horizontal(), "ligne de droite relativement "
                       f"horizontale ({horizontal.angle_to_horizontal():.0f}°)",
                       high=RELATIVE_AXIS_DEG, unit="deg")
    scoring["C"].add(goes_right, "la ligne horizontale part vers la droite")

    scoring["D"].limit(position, third, low=first, high=last, unit="part")

    scoring["E"].add(two_lines, f"seulement deux lignes ({len(lines)} trouvée(s))")
    scoring["E"].limit(gap, f"les deux lignes se rejoignent (intervalle {fmt(gap)})",
                       high=JUNCTION_MM)

    extras = extra_elements(drawing, [vertical, horizontal])
    scoring["F"].add(not extras, "aucun autre élément" if not extras
                     else f"{len(extras)} élément(s) en trop")
    lo, hi = LENGTH_RATIO
    scoring["F"].limit(ratio, f"rapport verticale / horizontale {fmt_ratio(ratio)} "
                       f"entre {lo.text} et {hi.text}", low=lo, high=hi, unit="ratio")

    return scoring.result()
