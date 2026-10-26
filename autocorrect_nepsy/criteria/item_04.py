"""Item 4 : carré.

Seuils repris du manuel NEPSY-II (Copie de figures), reformulés.
"""

from __future__ import annotations

import numpy as np

from .. import geometry as geo
from ..strokes import Drawing
from .base import ItemResult, Scoring, fmt, fmt_ratio, manual_thresholds, near_threshold
from . import marks as mk
from .shapes import check_lines, end_at, extra_elements, intersection, review_notes

# Seuils du manuel, reformulés (liste : autocorrect-nepsy seuils).
threshold = manual_thresholds(__name__)
GENERAL_MAX_RATIO = threshold(2.0, "G", "rapport du plus long au plus court côté, au plus",
                              "ratio")
MAX_INTERRUPTIONS = threshold(3, "A", "interruptions par ligne, au plus", "nombre")
STRAIGHT_BAND_MM = threshold(4.0, "A", "largeur de la barre grisée où tient chaque ligne")
OVERSHOOT_MM = threshold(5.0, "B", "dépassement à un coin qui compte (moins de deux admis)")
HORIZONTAL_SIDES_DEG = threshold(30.0, "C", "écart des côtés haut et bas à l'horizontale, au plus",
                                 "deg")
CORNER_RANGE = (threshold(60.0, "D", "angle d'un coin, au moins", "deg"),
                threshold(120.0, "D", "angle d'un coin, au plus", "deg"))
LOCAL_MAX_SIDE_MM = threshold(70.0, "F", "plus long côté, au plus")
LOCAL_MAX_RATIO = threshold(1.3, "F", "rapport du plus long au plus court côté, au plus", "ratio")


def score(drawing: Drawing, item: int = 4) -> ItemResult:
    scoring = Scoring(item, "GABCDEF")
    if drawing.is_empty:
        return scoring.empty()
    lines = drawing.significant_lines()
    horizontals = [l for l in lines if l.angle_to_horizontal() <= 45]
    verticals = [l for l in lines if l.angle_to_horizontal() > 45]
    scoring.measures["nombre_lignes"] = len(lines)
    scoring.notes += review_notes(lines)

    check_lines(scoring["A"], lines, STRAIGHT_BAND_MM, MAX_INTERRUPTIONS)
    scoring["E"].add(len(lines) == 4, f"seulement quatre lignes ({len(lines)} trouvée(s))")

    scoring.marks += [mk.bande(line) for line in lines]

    if len(horizontals) < 2 or len(verticals) < 2:
        reason = (f"figure à quatre côtés non reconnue ({len(horizontals)} côté(s) "
                  f"horizontal(aux), {len(verticals)} vertical(aux))")
        scoring.not_recognized(("G", "B", "C", "D", "F"), reason)
        return scoring.result()

    top, bottom = sorted(horizontals[:2], key=lambda l: l.center[1])
    left, right = sorted(verticals[:2], key=lambda l: l.center[0])
    corners = {
        "haut-gauche": (top, left), "haut-droit": (top, right),
        "bas-droit": (bottom, right), "bas-gauche": (bottom, left),
    }
    points = {name: intersection(a, b) for name, (a, b) in corners.items()}
    if any(p is None for p in points.values()):
        scoring.not_recognized(("G", "B", "C", "D", "F"),
                               "côtés parallèles : coins introuvables")
        return scoring.result()

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
    near_overshoots = any(near_threshold(o, OVERSHOOT_MM) for o in overshoots)
    ratio = max(sides.values()) / max(min(sides.values()), 1e-6)
    longest = max(sides.values())
    for (a, b), side in zip(((tl, tr), (br, bl), (bl, tl), (tr, br)), sides):
        scoring.marks.append(mk.cote(a, b, fmt(sides[side])))
    for name, (vertex, p1, p2) in {"haut-gauche": (tl, tr, bl), "haut-droit": (tr, tl, br),
                                    "bas-droit": (br, tr, bl), "bas-gauche": (bl, br, tl)}.items():
        scoring.marks.append(mk.angle(vertex, p1, p2, f"{angles[name]:.0f}°"))
    scoring.measures.update({f"cote_{k}_mm": float(v) for k, v in sides.items()})
    scoring.measures.update({f"angle_{k}_deg": v for k, v in angles.items()})
    scoring.measures["rapport_cotes"] = ratio
    extras = extra_elements(drawing, [top, bottom, left, right])

    scoring["G"].add(len(lines) == 4, f"quatre côtés nettement définis ({len(lines)} ligne(s))")
    scoring["G"].limit(ratio, f"rapport des côtés {fmt_ratio(ratio)} ≤ {GENERAL_MAX_RATIO.text}",
                       high=GENERAL_MAX_RATIO, unit="ratio")

    scoring["B"].add(big_overshoots < 2,
                     f"{big_overshoots} dépassement(s) de plus de {OVERSHOOT_MM.text} aux coins "
                     "(moins de 2)",
                     near=near_overshoots)

    scoring["C"].add(True, "forme carrée ou rectangulaire à quatre coins")
    for name, line in (("haut", top), ("bas", bottom)):
        angle = line.angle_to_horizontal()
        scoring["C"].limit(angle, f"côté {name} à {angle:.0f}° de l'horizontale "
                           f"(≤ {HORIZONTAL_SIDES_DEG.text})",
                           high=HORIZONTAL_SIDES_DEG, unit="deg")

    lo, hi = CORNER_RANGE
    for name, angle in angles.items():
        scoring["D"].limit(angle, f"coin {name} : {angle:.0f}° (entre {lo.text} et {hi.text})",
                           low=lo, high=hi, unit="deg")

    scoring["F"].add(not extras, "aucun autre élément" if not extras
                     else f"{len(extras)} élément(s) en trop")
    scoring["F"].limit(longest, f"plus long côté {fmt(longest)} ≤ {LOCAL_MAX_SIDE_MM.text}",
                       high=LOCAL_MAX_SIDE_MM)
    scoring["F"].limit(ratio, f"rapport des côtés {fmt_ratio(ratio)} ≤ {LOCAL_MAX_RATIO.text}",
                       high=LOCAL_MAX_RATIO, unit="ratio")

    return scoring.result()
