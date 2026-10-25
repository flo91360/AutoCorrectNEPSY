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
from .base import Checks, ItemResult, empty_result, fmt, fmt_ratio, not_recognized
from .polygons import (EDGE_OFFSET_MM, away_from, overshoot, polygon, raster, silhouette,
                       simplify, wavy_changes)
from .shapes import EXTRA_ELEMENT_MM

POLYGON_EPSILONS_MM = (1.0, 1.4, 1.8, 2.4)  # simplification du contour
WOBBLE_MM = 0.8  # amplitude d'une ondulation de la main (Motricité A)
MOTOR_MAX_CHANGES = 3  # Motricité A, sur toute la figure
JOIN_MM = 1.0  # Motricité B : intervalle ou dépassement aux intersections
STEPS = 4
GENERAL_MAX_LEFT_BASE = 1.5  # côté gauche / base
GENERAL_MAX_STEP_RATIO = 1.5  # plus long / plus court côté d'une marche
GLOBAL_BASE_DEG = 10.0  # Global C
GLOBAL_MAX_RISER_RATIO = 1.2  # Global D : marche la plus haute / la plus basse
RIGHT_ANGLE = (80.0, 100.0)  # Global D et Local F
LOCAL_MIN_BASE_MM = 30.0  # Local E
LOCAL_MAX_STEP_SIDE_MM = 25.0  # Local E
ON_OUTLINE_MM = 2.0  # encre plus éloignée du contour : autre élément


def score(drawing: Drawing, item: int = 18) -> ItemResult:
    codes = ("G", "A", "B", "C", "D", "E", "F")
    if drawing.is_empty:
        return empty_result(item, codes, "aucun tracé dans la zone")
    checks = {code: Checks() for code in codes}
    measures: dict[str, float] = {}
    marks: list = []
    notes: list[str] = []

    def result() -> ItemResult:
        return ItemResult(item, {c: checks[c].criterion(c) for c in codes}, measures, notes,
                          marks)

    outline = silhouette(drawing)
    found = None if outline is None else _stairs(outline)
    if found is None:
        reason = "escalier non reconnu (paliers et contremarches entre le haut à gauche et le bas à droite)"
        not_recognized(checks, codes, reason, notes)
        return result()
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
    measures.update({"marches": count, "base_mm": base, "cote_gauche_mm": left,
                     "base_angle_deg": base_angle})

    marks.append(mk.trace(np.vstack([v, v[:1]]), "contour lu", 0))
    marks.append(mk.cote(v[bl], v[br], f"base {fmt(base)} · {base_angle:.0f}°", side=(0.0, 1.0)))
    marks.append(mk.cote(v[tl], v[bl], f"gauche {fmt(left)}", side=(-1.0, 0.0)))
    for i, (a, b, c) in enumerate(steps, start=1):
        marks.append(mk.segment(v[b], v[c], f"marche {i} : {fmt(treads[i - 1], '')} × "
                                f"{fmt(risers[i - 1])}"))

    cores = [poly.core(k) for k in range(n)]
    changes = wavy_changes(geo.count_direction_changes(pts, WOBBLE_MM) for pts in cores
                           if len(pts) >= 3)
    checks["A"].add(changes <= MOTOR_MAX_CHANGES, f"{changes} changement(s) de direction sur "
                    "toute la figure (3 au plus)")
    r = raster(drawing)
    gaps = r.gaps if r is not None else []
    over = [overshoot(drawing, poly, k) for k in range(n)]
    worst = max(over + gaps)
    measures["jonction_max_mm"] = worst
    if over and max(over) > 0.5:
        k = int(np.argmax(over))
        marks.append(mk.point(v[k], f"dépasse {fmt(over[k])}"))
    checks["B"].limit(worst, f"plus grand intervalle ou dépassement aux intersections {fmt(worst)} "
                      "≤ 1 mm", high=JOIN_MM)

    rounded = poly.rounded()
    for k, gap in rounded:
        marks.append(mk.point(v[k], f"coin arrondi {fmt(gap)}"))
    step_ratios = [max(t, s) / max(min(t, s), 1e-6) for t, s in zip(treads, risers)]
    general = checks["G"]
    general.add(count == STEPS, f"{count} marche(s) (exactement 4)")
    general.add(not rounded, "angles ni pincés ni arrondis" if not rounded
                else f"{len(rounded)} angle(s) arrondi(s)")
    left_base = left / max(base, 1e-6)
    general.limit(left_base, f"côté gauche {fmt(left)} / base {fmt(base)} : {fmt_ratio(left_base)} "
                  "≤ 1,5:1", high=GENERAL_MAX_LEFT_BASE, unit="ratio")
    worst_step = max(step_ratios)
    general.limit(worst_step, f"marche la moins régulière : plus long / plus court côté "
                  f"{fmt_ratio(worst_step)} ≤ 1,5:1", high=GENERAL_MAX_STEP_RATIO, unit="ratio")

    checks["C"].add(count >= 2, f"figure en marches d'escalier ({count} marche(s))")
    checks["C"].limit(base_angle, f"base à {base_angle:.0f}° de l'horizontale (≤ 10°)",
                      high=GLOBAL_BASE_DEG, unit="deg")

    riser_ratio = max(risers) / max(min(risers), 1e-6)
    measures["rapport_hauteurs_marches"] = riser_ratio
    checks["D"].limit(riser_ratio, f"hauteurs des marches {_list(risers)} : plus haute / plus "
                      f"basse {fmt_ratio(riser_ratio)} ≤ 1,2:1", high=GLOBAL_MAX_RISER_RATIO,
                      unit="ratio")
    lo, hi = RIGHT_ANGLE
    for name, k in (("haut-gauche", tl), ("haut de la première marche", chain[1]),
                    ("bas-gauche", bl), ("bas-droit", br)):
        angle = _corner_angle(v, k)
        checks["D"].limit(angle, f"angle {name} : {angle:.0f}° (entre 80° et 100°)", low=lo,
                          high=hi, unit="deg")

    checks["E"].add(count == STEPS, f"{count} marche(s) (exactement 4)")
    checks["E"].limit(base, f"base {fmt(base)} ≥ 30 mm", low=LOCAL_MIN_BASE_MM)
    longest = max(treads + risers)
    checks["E"].limit(longest, f"plus long côté de marche {fmt(longest)} ≤ 25 mm",
                      high=LOCAL_MAX_STEP_SIDE_MM)

    extra = away_from(drawing, [outline], ON_OUTLINE_MM)
    extras = max(0, count - STEPS) + int(extra >= EXTRA_ELEMENT_MM) + sum(
        size >= EXTRA_ELEMENT_MM for size in drawing.component_sizes[1:])
    checks["F"].add(extras == 0, "aucun autre élément" if not extras
                    else f"{extras} élément(s) en trop (marches au-delà de 4 comprises)")
    step_corners = [k for k in chain[2:-1] if k not in (tl, br)]
    rounded_steps = [k for k, _ in rounded if k in step_corners]
    checks["F"].add(not rounded_steps, "aucun angle de marche arrondi" if not rounded_steps
                    else f"{len(rounded_steps)} angle(s) de marche arrondi(s)")
    for k in step_corners:
        angle = _corner_angle(v, k)
        checks["F"].limit(angle, f"angle de marche : {angle:.0f}° (entre 80° et 100°)", low=lo,
                          high=hi, unit="deg")
    return result()


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
