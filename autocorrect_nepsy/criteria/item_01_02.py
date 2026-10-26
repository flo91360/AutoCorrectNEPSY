"""Items 1 (trait vertical) et 2 (trait horizontal).

Seuils repris du manuel NEPSY-II (Copie de figures), reformulés.
"""

from __future__ import annotations

import numpy as np

from .. import geometry as geo
from ..strokes import Drawing, StraightLine
from .base import ItemResult, Scoring, fmt, manual_thresholds
from . import marks as mk

# Seuils du manuel, reformulés (liste : autocorrect-nepsy seuils).
threshold = manual_thresholds(__name__)
GENERAL_MIN_MM = threshold(7.0, "G", "longueur du trait, au moins")
GENERAL_CONE = threshold(30.0, "G", "écart à l'axe de la plus grande part du trait, au plus",
                         "deg")
GENERAL_MIN_PART = threshold(0.5, "G", "part du trait dans cet écart à l'axe, au moins", "part")
MOTOR_MIN_MM = threshold(10.0, "A", "longueur du trait, au moins")
STRAIGHT_BAND_MM = threshold(5.0, "B", "largeur de la barre grisée où tient le trait")
GLOBAL_CONE = threshold(45.0, "C", "écart à l'axe de tout le trait, au plus", "deg")
GLOBAL_MIN_MM = threshold(20.0, "D", "longueur du trait, au moins")
ITEM2_MAX_MM = threshold(70.0, "D", "longueur du trait horizontal (item 2), au plus")
# Réglages de l'outil (reconnaissance des figures, tolérances de mesure).
# Près du sommet de l'angle, la direction d'un point n'est pas fiable.
APEX_IGNORE_MM = 3.0


def score(drawing: Drawing, item: int) -> ItemResult:
    scoring = Scoring(item, "GABCD")
    if drawing.is_empty or not drawing.lines:
        return scoring.empty()
    line, notes = _trace(drawing)
    scoring.notes.extend(notes)
    if item == 1:
        axis, name, deviation = np.array([0.0, 1.0]), "la verticale", line.angle_to_vertical()
    else:
        axis, name, deviation = np.array([1.0, 0.0]), "l'horizontale", line.angle_to_horizontal()
    in_cone_30 = max(geo.fraction_in_cone(line.points, end, axis, GENERAL_CONE) for end in line.ends)
    widest = min(geo.max_cone_angle(line.points, end, axis, APEX_IGNORE_MM) for end in line.ends)
    length = line.length

    scoring["G"].limit(length, f"longueur {fmt(length)} ≥ {GENERAL_MIN_MM.text}",
                       low=GENERAL_MIN_MM)
    scoring["G"].limit(in_cone_30, f"{in_cone_30:.0%} du trait à moins de {GENERAL_CONE.text} "
                       f"de {name} (plus de la moitié exigée)", low=GENERAL_MIN_PART, unit="part")

    scoring["A"].limit(length, f"longueur {fmt(length)} ≥ {MOTOR_MIN_MM.text}", low=MOTOR_MIN_MM)
    scoring["B"].limit(line.width, f"trait droit : tient dans une bande de {fmt(line.width)} "
                       f"(≤ {STRAIGHT_BAND_MM.text})", high=STRAIGHT_BAND_MM)

    scoring["C"].limit(widest, f"tout le trait à moins de {GLOBAL_CONE.text} de {name} (écart "
                       f"maximal {widest:.0f}°)", high=GLOBAL_CONE, unit="deg")
    scoring["D"].limit(length, f"longueur {fmt(length)} ≥ {GLOBAL_MIN_MM.text}", low=GLOBAL_MIN_MM)
    if item == 2:
        scoring["D"].limit(length, f"longueur {fmt(length)} ≤ {ITEM2_MAX_MM.text}",
                           high=ITEM2_MAX_MM)

    # Écart à l'axe mesuré depuis l'extrémité haute (item 1) ou gauche (item 2).
    start, end = sorted(line.ends, key=lambda p: p[1] if item == 1 else p[0])
    scoring.marks += [mk.line_length(line), mk.bande(line),
                      mk.angle(start, start + axis * min(15.0, length), end,
                               f"{deviation:.0f}° / {'verticale' if item == 1 else 'horizontale'}")]
    scoring.measures.update(longueur_mm=length, ecart_axe_deg=deviation,
                            largeur_bande_mm=line.width)
    return scoring.result()


def _trace(drawing: Drawing) -> tuple[StraightLine, list[str]]:
    """Le trait noté : le ou les traits continus qui portent la plus longue ligne
    droite, en entier (un zigzag, une ondulation ou un crochet en font partie, et
    comptent pour la longueur, la barre grisée et l'écart à l'axe).

    Un trait brisé en plusieurs lignes droites, ou d'autres traits dans la zone,
    sont signalés : la règle du manuel les tranche mal.
    """
    longest = drawing.lines[0]
    strokes = [s.points for s in drawing.strokes
               if any(_shares(s.points, piece) for piece in longest.pieces)]
    trace = StraightLine(strokes or longest.pieces, drawing.stroke_width)
    lines = drawing.significant_lines()
    inside = [l for l in lines if any(_shares(s, piece) for s in strokes for piece in l.pieces)]
    notes = []
    if len(inside) > 1:
        notes.append(f"trait brisé ou en zigzag ({len(inside)} morceaux droits) : mesuré en "
                     "entier, vérifier la cotation")
    if len(lines) > len(inside):
        notes.append(f"{len(lines) - len(inside)} trait(s) en plus du trait noté : vérifier la "
                     "cotation")
    return trace, notes


def _shares(points: np.ndarray, piece: np.ndarray) -> bool:
    """Le morceau fait partie de ce trait (même point au milieu du morceau)."""
    middle = piece[len(piece) // 2]
    return bool(np.min(np.abs(points - middle).sum(axis=1)) < 1e-9)
