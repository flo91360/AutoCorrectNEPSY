"""Items 1 (trait vertical) et 2 (trait horizontal).

Seuils repris du manuel NEPSY-II (Copie de figures), reformulés.
"""

from __future__ import annotations

import numpy as np

from .. import geometry as geo
from ..strokes import Drawing
from .base import Checks, ItemResult, empty_result, fmt
from . import marks as mk

GENERAL_MIN_MM = 7.0  # trace d'au moins 7 mm
GENERAL_CONE = 30.0  # plus de la moitié du trait à moins de 30° de l'axe
MOTOR_MIN_MM = 10.0  # Motricité A : au moins 1 cm
STRAIGHT_BAND_MM = 5.0  # Motricité B : tient dans la barre grisée de 5 mm
GLOBAL_CONE = 45.0  # Global C : tout le trait à moins de 45° de l'axe
GLOBAL_MIN_MM = 20.0  # Global D : au moins 2 cm
ITEM2_MAX_MM = 70.0  # Global D (item 2) : au plus 7 cm
# Près du sommet de l'angle, la direction d'un point n'est pas fiable.
APEX_IGNORE_MM = 3.0


def score(drawing: Drawing, item: int) -> ItemResult:
    if drawing.is_empty or not drawing.lines:
        return empty_result(item, ("G", "A", "B", "C", "D"), "aucun tracé dans la zone")
    line = drawing.lines[0]
    if item == 1:
        axis, name, deviation = np.array([0.0, 1.0]), "la verticale", line.angle_to_vertical()
    else:
        axis, name, deviation = np.array([1.0, 0.0]), "l'horizontale", line.angle_to_horizontal()
    in_cone_30 = max(geo.fraction_in_cone(line.points, end, axis, GENERAL_CONE) for end in line.ends)
    widest = min(geo.max_cone_angle(line.points, end, axis, APEX_IGNORE_MM) for end in line.ends)
    length = line.length

    general = Checks()
    general.limit(length, f"longueur {fmt(length)} ≥ 7 mm", low=GENERAL_MIN_MM)
    general.limit(in_cone_30, f"{in_cone_30:.0%} du trait à moins de 30° de {name} "
                  "(plus de la moitié exigée)", low=0.5, unit="part")

    motor_a = Checks().limit(length, f"longueur {fmt(length)} ≥ 10 mm", low=MOTOR_MIN_MM)
    motor_b = Checks().limit(line.width, f"trait droit : tient dans une bande de "
                             f"{fmt(line.width)} (≤ 5 mm)", high=STRAIGHT_BAND_MM)

    global_c = Checks().limit(widest, f"tout le trait à moins de 45° de {name} (écart "
                              f"maximal {widest:.0f}°)", high=GLOBAL_CONE, unit="deg")
    global_d = Checks().limit(length, f"longueur {fmt(length)} ≥ 20 mm", low=GLOBAL_MIN_MM)
    if item == 2:
        global_d.limit(length, f"longueur {fmt(length)} ≤ 70 mm", high=ITEM2_MAX_MM)

    # Écart à l'axe mesuré depuis l'extrémité haute (item 1) ou gauche (item 2).
    start, end = sorted(line.ends, key=lambda p: p[1] if item == 1 else p[0])
    marks = [mk.line_length(line), mk.bande(line),
             mk.angle(start, start + axis * min(15.0, length), end,
                      f"{deviation:.0f}° / {'verticale' if item == 1 else 'horizontale'}")]

    # Seule la plus longue ligne est notée : un trait brisé ou en zigzag, ou un
    # trait en trop, donne plusieurs lignes et la note peut ne pas le refléter.
    count = len(drawing.significant_lines())
    notes = [] if count <= 1 else [
        f"{count} lignes dans la zone (trait brisé, en zigzag ou trait en trop) : seule la "
        "plus longue est notée, vérifier la cotation"]

    return ItemResult(
        item,
        {"G": general.criterion("G"), "A": motor_a.criterion("A"),
         "B": motor_b.criterion("B"), "C": global_c.criterion("C"),
         "D": global_d.criterion("D")},
        measures={"longueur_mm": length, "ecart_axe_deg": deviation,
                  "largeur_bande_mm": line.width},
        notes=notes,
        marks=marks,
    )
