"""Item 18 : escalier à quatre marches.

Seuils repris du manuel NEPSY-II (Copie de figures), reformulés.

La silhouette de la figure est simplifiée en polygone ; on y repère les coins
haut-gauche, bas-gauche et bas-droit, puis le profil des marches entre le
coin haut-gauche et le coin bas-droit (alternance de paliers et de
contremarches).
"""

from __future__ import annotations

import numpy as np

from .. import geometry as geo
from ..strokes import Drawing
from . import marks as mk
from .base import ItemResult, Scoring, fmt, fmt_ratio, manual_thresholds
from .polygons import (EDGE_OFFSET_MM, away_from, overshoot, polygon, raster, silhouette,
                       simplify, wavy_changes)
from .shapes import EXTRA_ELEMENT_MM

# Seuils du manuel, reformulés (liste : autocorrect-nepsy seuils).
threshold = manual_thresholds(__name__)
MOTOR_MAX_CHANGES = threshold(3, "A", "changements de direction sur toute la figure, au plus",
                              "nombre")
JOIN_MM = threshold(1.0, "B", "intervalle ou dépassement aux intersections, au plus")
STEPS = threshold(4, "GEF", "nombre de marches, exactement", "nombre")
GENERAL_MAX_LEFT_BASE = threshold(1.5, "G", "rapport du côté gauche à la base, au plus", "ratio")
GENERAL_MAX_STEP_RATIO = threshold(1.5, "G", "rapport du plus long au plus court côté de chaque "
                                   "marche, au plus", "ratio")
GLOBAL_BASE_DEG = threshold(10.0, "C", "écart de la base à l'horizontale, au plus", "deg")
GLOBAL_MAX_RISER_RATIO = threshold(1.2, "D", "rapport de la plus haute à la plus basse marche, "
                                   "au plus", "ratio")
RIGHT_ANGLE = (threshold(80.0, "DF", "angle droit des coins et des marches, au moins", "deg"),
               threshold(100.0, "DF", "angle droit des coins et des marches, au plus", "deg"))
LOCAL_MIN_BASE_MM = threshold(30.0, "E", "longueur de la base, au moins")
LOCAL_MAX_STEP_SIDE_MM = threshold(25.0, "E", "plus long côté de marche, au plus")
# Réglages de l'outil (reconnaissance des figures, tolérances de mesure).
POLYGON_EPSILONS_MM = (1.0, 1.4, 1.8, 2.4)  # simplification du contour
WOBBLE_MM = 0.8  # amplitude d'une ondulation de la main (Motricité A)
ON_OUTLINE_MM = 2.0  # encre plus éloignée du contour : autre élément


def score(drawing: Drawing, item: int = 18) -> ItemResult:
    scoring = Scoring(item, "GABCDEF")
    if drawing.is_empty:
        return scoring.empty()

    outline = silhouette(drawing)
    found = None if outline is None else _stairs(outline)
    if found is None:
        reason = "escalier non reconnu (paliers et contremarches entre le haut à gauche et le bas à droite)"
        scoring.not_recognized(scoring.codes, reason)
        return scoring.result()
    poly, tl, br, bl = found
    v = poly.vertices
    n = len(v)
    chain = [(tl + i) % n for i in range((br - tl) % n + 1)]
    steps = [(chain[i], chain[i + 1], chain[i + 2]) for i in range(0, len(chain) - 2, 2)]
    treads = [float(np.linalg.norm(v[b] - v[a])) for a, b, _ in steps]
    risers = [float(np.linalg.norm(v[c] - v[b])) for _, b, c in steps]
    base = float(np.linalg.norm(v[bl] - v[br]))
    left = float(np.linalg.norm(v[tl] - v[bl]))
    base_angle = geo.angle_to_horizontal(v[bl] - v[br])
    count = len(steps)
    scoring.measures.update({"marches": count, "base_mm": base, "cote_gauche_mm": left,
                             "base_angle_deg": base_angle})

    scoring.marks.append(mk.trace(np.vstack([v, v[:1]]), "contour lu", 0))
    scoring.marks.append(mk.cote(v[bl], v[br], f"base {fmt(base)} · {base_angle:.0f}°",
                                 side=(0.0, 1.0)))
    scoring.marks.append(mk.cote(v[tl], v[bl], f"gauche {fmt(left)}", side=(-1.0, 0.0)))
    for i, (a, b, c) in enumerate(steps, start=1):
        scoring.marks.append(mk.segment(v[b], v[c], f"marche {i} : {fmt(treads[i - 1], '')} × "
                                        f"{fmt(risers[i - 1])}"))

    cores = [poly.core(k) for k in range(n)]
    changes = wavy_changes(geo.count_direction_changes(pts, WOBBLE_MM) for pts in cores
                           if len(pts) >= 3)
    scoring["A"].add(changes <= MOTOR_MAX_CHANGES, f"{changes} changement(s) de direction sur "
                     f"toute la figure ({MOTOR_MAX_CHANGES.text} au plus)")
    r = raster(drawing)
    gaps = r.gaps if r is not None else []
    over = [overshoot(drawing, poly, k) for k in range(n)]
    worst = max(over + gaps)
    scoring.measures["jonction_max_mm"] = worst
    if over and max(over) > 0.5:
        k = int(np.argmax(over))
        scoring.marks.append(mk.point(v[k], f"dépasse {fmt(over[k])}"))
    scoring["B"].limit(worst, f"plus grand intervalle ou dépassement aux intersections {fmt(worst)} "
                       f"≤ {JOIN_MM.text}", high=JOIN_MM)

    rounded = poly.rounded()
    for k, gap in rounded:
        scoring.marks.append(mk.point(v[k], f"coin arrondi {fmt(gap)}"))
    step_ratios = [max(t, s) / max(min(t, s), 1e-6) for t, s in zip(treads, risers)]
    general = scoring["G"]
    general.add(count == STEPS, f"{count} marche(s) (exactement {STEPS.text})")
    general.add(not rounded, "angles ni pincés ni arrondis" if not rounded
                else f"{len(rounded)} angle(s) arrondi(s)")
    left_base = left / max(base, 1e-6)
    general.limit(left_base, f"côté gauche {fmt(left)} / base {fmt(base)} : {fmt_ratio(left_base)} "
                  f"≤ {GENERAL_MAX_LEFT_BASE.text}", high=GENERAL_MAX_LEFT_BASE, unit="ratio")
    worst_step = max(step_ratios)
    general.limit(worst_step, f"marche la moins régulière : plus long / plus court côté "
                  f"{fmt_ratio(worst_step)} ≤ {GENERAL_MAX_STEP_RATIO.text}",
                  high=GENERAL_MAX_STEP_RATIO, unit="ratio")

    scoring["C"].add(count >= 2, f"figure en marches d'escalier ({count} marche(s))")
    scoring["C"].limit(base_angle, f"base à {base_angle:.0f}° de l'horizontale "
                       f"(≤ {GLOBAL_BASE_DEG.text})",
                       high=GLOBAL_BASE_DEG, unit="deg")

    riser_ratio = max(risers) / max(min(risers), 1e-6)
    scoring.measures["rapport_hauteurs_marches"] = riser_ratio
    scoring["D"].limit(riser_ratio, f"hauteurs des marches {_list(risers)} : plus haute / plus "
                       f"basse {fmt_ratio(riser_ratio)} ≤ {GLOBAL_MAX_RISER_RATIO.text}",
                       high=GLOBAL_MAX_RISER_RATIO,
                       unit="ratio")
    lo, hi = RIGHT_ANGLE
    for name, k in (("haut-gauche", tl), ("haut de la première marche", chain[1]),
                    ("bas-gauche", bl), ("bas-droit", br)):
        angle = _corner_angle(v, k)
        scoring["D"].limit(angle, f"angle {name} : {angle:.0f}° (entre {lo.text} et {hi.text})",
                           low=lo, high=hi, unit="deg")

    scoring["E"].add(count == STEPS, f"{count} marche(s) (exactement {STEPS.text})")
    scoring["E"].limit(base, f"base {fmt(base)} ≥ {LOCAL_MIN_BASE_MM.text}", low=LOCAL_MIN_BASE_MM)
    longest = max(treads + risers)
    scoring["E"].limit(longest, f"plus long côté de marche {fmt(longest)} ≤ "
                       f"{LOCAL_MAX_STEP_SIDE_MM.text}",
                       high=LOCAL_MAX_STEP_SIDE_MM)

    extra = away_from(drawing, [outline], ON_OUTLINE_MM)
    extras = max(0, count - STEPS) + int(extra >= EXTRA_ELEMENT_MM) + sum(
        size >= EXTRA_ELEMENT_MM for size in drawing.component_sizes[1:])
    scoring["F"].add(extras == 0, "aucun autre élément" if not extras
                     else f"{extras} élément(s) en trop (marches au-delà de {STEPS.text} "
                     "comprises)")
    step_corners = [k for k in chain[2:-1] if k not in (tl, br)]
    rounded_steps = [k for k, _ in rounded if k in step_corners]
    scoring["F"].add(not rounded_steps, "aucun angle de marche arrondi" if not rounded_steps
                     else f"{len(rounded_steps)} angle(s) de marche arrondi(s)")
    for k in step_corners:
        angle = _corner_angle(v, k)
        scoring["F"].limit(angle, f"angle de marche : {angle:.0f}° (entre {lo.text} et "
                           f"{hi.text})", low=lo, high=hi, unit="deg")
    return scoring.result()


def _stairs(outline: np.ndarray):
    """Polygone de l'escalier et indices des coins haut-gauche, bas-droit et
    bas-gauche, si le profil entre le haut-gauche et le bas-droit alterne
    paliers et contremarches."""
    for epsilon in POLYGON_EPSILONS_MM:
        corners = _merge_aligned(outline, simplify(outline, epsilon))
        if len(corners) < 6:
            continue
        poly = polygon(outline, corners, -EDGE_OFFSET_MM)
        v = poly.vertices
        n = len(v)
        tl = int(np.argmin(v[:, 0] + v[:, 1]))
        br = int(np.argmax(v[:, 0] + v[:, 1]))
        bl = int(np.argmax(v[:, 1] - v[:, 0]))
        if (bl - br) % n != 1 or (tl - bl) % n != 1:
            continue
        chain = [(tl + i) % n for i in range((br - tl) % n + 1)]
        if len(chain) % 2 == 0:
            continue
        kinds = [_is_horizontal(v[chain[i + 1]] - v[chain[i]]) for i in range(len(chain) - 1)]
        if all(kinds[i] == (i % 2 == 0) for i in range(len(kinds))):
            return poly, tl, br, bl
    return None


def _merge_aligned(outline: np.ndarray, corners: np.ndarray) -> np.ndarray:
    """Retire les sommets entre deux côtés de même orientation (horizontale
    ou verticale) : une marche ondulée ne compte pas double."""
    corners = list(corners)
    changed = True
    while changed and len(corners) > 3:
        changed = False
        for i in range(len(corners)):
            a, b, c = outline[corners[i - 1]], outline[corners[i]], outline[corners[(i + 1) % len(corners)]]
            if _is_horizontal(b - a) == _is_horizontal(c - b) and geo.angle_between(b - a, c - b) < 45:
                del corners[i]
                changed = True
                break
    return np.array(corners)


def _is_horizontal(vector: np.ndarray) -> bool:
    return geo.angle_to_horizontal(vector) <= 45


def _corner_angle(v: np.ndarray, k: int) -> float:
    """Angle (0 à 180°) entre les deux côtés qui se rejoignent au coin ``k``."""
    n = len(v)
    return geo.angle_between(v[k - 1] - v[k], v[(k + 1) % n] - v[k])


def _list(values: list[float]) -> str:
    return ", ".join(fmt(x, "") for x in values) + " mm"
