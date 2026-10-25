"""Item 19 : cylindre debout (seau), deux ellipses concentriques en haut,
une ellipse de base et deux lignes verticales.

Seuils repris du manuel NEPSY-II (Copie de figures), reformulés.

Les ellipses sont cherchées parmi les traits ; l'ellipse supérieure externe,
souvent tremblée, est cherchée concentrique à l'interne. De l'ellipse de
base, seuls l'avant et la partie vue dans l'ouverture sont dessinés.
"""

from __future__ import annotations

import cv2
import numpy as np

from .. import geometry as geo
from ..strokes import STEP_MM, Drawing, StraightLine
from . import marks as mk
from .base import Checks, ItemResult, empty_result, fmt, fmt_ratio
from .ellipses import Ellipse, concentric, crosses, find_ellipses, straightest
from .shapes import EXTRA_ELEMENT_MM, separate_extras

JOIN_MM = 1.0  # Général et Motricité A : intervalle aux jonctions
GAP_MM = 1.0  # Motricité A : intervalle dans une ellipse
STRAIGHT_MAX_MM = 7.0  # Motricité B : portion d'ellipse droite
DISTORTION_MAX_SPREAD = 0.08  # irrégularité du rayon d'une ellipse (bosses, angles)
RING_MAX_MM = 1.0  # Général et Local E : l'ellipse de base entre dans l'anneau du haut
VERTICAL_MAX_DEG = 25.0  # lignes verticales
VERTICAL_NEAR_MM = 6.0  # une verticale part du côté de l'ellipse externe
ON_ELLIPSE_MM = 1.2  # point d'une ellipse (pas d'une verticale)
MIN_OVERLAP_MM = 2.0  # Global C : chevauchement base / ellipse interne
HORIZONTAL_LOOSE_DEG = 20.0  # Global C : grands axes « relativement » horizontaux
AXIS_MAX_DEG = 5.0  # Global D
GLOBAL_MAX_MINOR_RATIO = 1.2  # Global D : petits axes externe / base
CIRCLE_MAX_RATIO = 1.1  # Local E et F : en deçà, c'est un cercle et non une ellipse
LOCAL_MAX_AXIS_RATIO = 1.4  # Local F : externe / interne
RASTER_PX_PER_MM = 8.0
ON_FIGURE_MM = 2.0


def score(drawing: Drawing, item: int = 19) -> ItemResult:
    codes = ("G", "A", "B", "C", "D", "E", "F")
    if drawing.is_empty:
        return empty_result(item, codes, "aucun tracé dans la zone")
    checks = {code: Checks() for code in codes}
    measures: dict[str, float] = {}
    marks: list = []

    def result() -> ItemResult:
        return ItemResult(item, {c: checks[c].criterion(c) for c in codes}, measures, marks=marks)

    found = _bucket(drawing)
    if found is None:
        reason = "cylindre non reconnu (deux ellipses concentriques au-dessus d'une ellipse de base)"
        for code in codes:
            checks[code].fail(reason)
        return result()
    outer, inner, base = found
    ellipses = {"supérieure externe": outer, "supérieure interne": inner, "de base": base}
    verticals = _verticals(drawing, [outer, inner, base], outer, base)
    for color, (name, e) in enumerate(ellipses.items()):
        marks.append(mk.trace(e.at(np.linspace(0, 2 * np.pi, 120)), f"ellipse {name}", color))
        marks.append(mk.segment(e.center - e.major_axis * e.major / 2,
                                e.center + e.major_axis * e.major / 2,
                                f"{fmt(e.major, '')} × {fmt(e.minor)} · {_tilt(e):.0f}°"))
    for line in verticals:
        marks.append(mk.bande(line, f"verticale {fmt(line.length)}", at="bout"))
    measures.update({f"{k}_grand_mm": e.major for k, e in (("externe", outer), ("interne", inner),
                                                          ("base", base))})
    measures.update({f"{k}_petit_mm": e.minor for k, e in (("externe", outer), ("interne", inner),
                                                          ("base", base))})

    # Jonctions des verticales avec l'ellipse externe (haut) et la base (bas).
    joins = []
    for line in verticals:
        top, bottom = sorted(line.ends, key=lambda p: p[1])
        joins += [_reach(top, outer), _reach(bottom, base)]
    join = max(joins) if joins else float("inf")
    ring = _ring_depth(base, outer, inner)
    crossing = crosses(base, outer) and crosses(base, inner)
    distorted = [n for n, e in ellipses.items() if e.spread > DISTORTION_MAX_SPREAD]
    measures.update({"jonction_max_mm": join, "base_dans_anneau_mm": ring})

    general = checks["G"]
    general.add(len(verticals) == 2, f"cylindre : trois ellipses reliées par {len(verticals)} "
                "verticale(s) (deux attendues)")
    general.add(not distorted, "ellipses sans distorsion majeure" if not distorted
                else f"distorsion de l'ellipse {', '.join(distorted)}")
    general.add(base.center[1] > inner.center[1], "deux ellipses concentriques au-dessus de "
                "l'ellipse de base")
    general.limit(join, f"plus grand intervalle aux jonctions des verticales {fmt(join)} ≤ 1 mm",
                  high=JOIN_MM)
    general.add(crossing, "l'ellipse de base recoupe les deux ellipses du haut" if crossing
                else "l'ellipse de base ne recoupe pas les deux ellipses du haut")
    general.limit(ring, f"l'ellipse de base entre de {fmt(ring)} dans l'anneau du haut (≤ 1 mm)",
                  high=RING_MAX_MM)

    gaps = {n: _gap(e, base is e, outer) for n, e in ellipses.items()}
    worst_gap = max(gaps.values())
    checks["A"].limit(worst_gap, f"plus grand intervalle dans une ellipse {fmt(worst_gap)} ≤ 1 mm",
                      high=GAP_MM)
    checks["A"].limit(join, f"plus grand intervalle aux jonctions des verticales {fmt(join)} "
                      "≤ 1 mm", high=JOIN_MM)
    straight = max(straightest(e) for e in ellipses.values())
    measures["portion_droite_max_mm"] = straight
    checks["B"].limit(straight, f"plus longue portion droite d'ellipse {fmt(straight)} ≤ 7 mm",
                      high=STRAIGHT_MAX_MM)

    overlap = _overlap(base, inner)
    measures["chevauchement_mm"] = overlap
    tilts = {n: _tilt(e) for n, e in ellipses.items()}
    checks["C"].add(len(verticals) == 2, f"forme cylindrique : deux ellipses concentriques en "
                    f"haut, une ellipse de base, {len(verticals)} verticale(s)")
    checks["C"].limit(overlap, f"chevauchement de la base et de l'ellipse interne {fmt(overlap)} "
                      "≥ 2 mm", low=MIN_OVERLAP_MM)
    for name, tilt in tilts.items():
        checks["C"].limit(tilt, f"grand axe de l'ellipse {name} à {tilt:.0f}° de l'horizontale "
                          "(relativement horizontal)", high=HORIZONTAL_LOOSE_DEG, unit="deg")

    for name, tilt in tilts.items():
        checks["D"].limit(tilt, f"axes de l'ellipse {name} à {tilt:.0f}° de l'horizontale et de "
                          "la verticale (≤ 5°)", high=AXIS_MAX_DEG, unit="deg")
    minor_ratio = max(outer.minor, base.minor) / max(min(outer.minor, base.minor), 1e-6)
    checks["D"].limit(minor_ratio, f"petits axes de l'ellipse externe {fmt(outer.minor)} et de la "
                      f"base {fmt(base.minor)} : {fmt_ratio(minor_ratio)} ≤ 1,2:1",
                      high=GLOBAL_MAX_MINOR_RATIO, unit="ratio")

    circles = [n for n, e in ellipses.items() if e.ratio < CIRCLE_MAX_RATIO]
    not_circles = "ellipses et non cercles" if not circles else f"cercle(s) : {', '.join(circles)}"
    checks["E"].add(not circles, not_circles)
    checks["E"].add(True, "deux ellipses concentriques et une ellipse de base distincte")
    checks["E"].limit(ring, f"l'ellipse de base entre de {fmt(ring)} dans l'anneau du haut "
                      "(≤ 1 mm)", high=RING_MAX_MM)

    used = np.vstack([e.points for e in ellipses.values()] + [l.points for l in verticals])
    extra = _away(drawing, used)
    extras = int(extra >= EXTRA_ELEMENT_MM) + len(separate_extras(drawing, used))
    checks["F"].add(extras == 0, "aucun autre élément" if not extras
                    else f"{extras} élément(s) en trop")
    checks["F"].add(not circles, not_circles)
    for axis, a, b in (("grand", outer.major, inner.major), ("petit", outer.minor, inner.minor)):
        ratio = a / max(b, 1e-6)
        checks["F"].limit(ratio, f"{axis} axe externe {fmt(a)} / interne {fmt(b)} : "
                          f"{fmt_ratio(ratio)} ≤ 1,4:1", high=LOCAL_MAX_AXIS_RATIO, unit="ratio")
    return result()


def _bucket(drawing: Drawing) -> tuple[Ellipse, Ellipse, Ellipse] | None:
    """Ellipses supérieure externe, supérieure interne et de base."""
    found = find_ellipses(drawing, 4)
    if len(found) < 2:
        return None
    best = None
    for upper in found:
        partner = concentric(drawing, upper, exclude=upper.points)
        if partner is None:
            continue
        pair = sorted((upper, partner), key=lambda e: e.major)
        below = [e for e in found if e is not upper and e.center[1] > upper.center[1] + 0.3 * upper.minor
                 and np.linalg.norm(e.center - partner.center) > 0.2 * upper.minor]
        if not below:
            continue
        base = max(below, key=lambda e: e.coverage)
        score = upper.coverage + partner.coverage + base.coverage
        if best is None or score > best[0]:
            best = (score, pair[1], pair[0], base)
    return None if best is None else best[1:]


def _tilt(e: Ellipse) -> float:
    return geo.angle_to_horizontal(e.major_axis)


def _verticals(drawing: Drawing, ellipses: list[Ellipse], outer: Ellipse,
               base: Ellipse) -> list[StraightLine]:
    """Ligne verticale gauche et droite entre l'ellipse externe et la base :
    points hors des ellipses, au tracé localement vertical, près des côtés de
    l'ellipse externe."""
    points, tangents = drawing.points, _tangents(drawing)
    off = np.ones(len(points), bool)
    for e in ellipses:
        off &= e.distance(points) > ON_ELLIPSE_MM
    upright = np.abs(tangents[:, 1]) >= np.cos(np.radians(VERTICAL_MAX_DEG))
    between = (points[:, 1] > outer.center[1] - 0.2 * outer.minor) & (
        points[:, 1] < base.center[1] + 0.2 * base.minor)
    found = []
    for side in (-1, 1):
        x = outer.center[0] + side * outer.major / 2
        near = off & upright & between & (np.abs(points[:, 0] - x) <= VERTICAL_NEAR_MM)
        if near.sum() >= 10:
            chosen = points[near]
            found.append(StraightLine([chosen[np.argsort(chosen[:, 1])]], drawing.stroke_width))
    return found


def _tangents(drawing: Drawing) -> np.ndarray:
    """Direction locale du tracé en chaque point (sur ~2 mm)."""
    found = []
    for stroke in drawing.strokes:
        pts = stroke.points
        k = min(3, len(pts) - 1)
        d = (np.vstack([pts[k:], np.repeat(pts[-1:], k, axis=0)])
             - np.vstack([np.repeat(pts[:1], k, axis=0), pts[:-k]]))
        found.append(d / np.maximum(np.linalg.norm(d, axis=1, keepdims=True), 1e-9))
    return np.vstack(found)


def _reach(point: np.ndarray, ellipse: Ellipse) -> float:
    """Intervalle entre le bout d'une verticale et le tracé de l'ellipse
    (un dépassement n'est pas un intervalle)."""
    if not len(ellipse.points):
        return float("inf")
    return float(np.linalg.norm(ellipse.points - point, axis=1).min())


def _ring_depth(base: Ellipse, outer: Ellipse, inner: Ellipse) -> float:
    """Profondeur (mm) dont le tracé de la base entre dans l'anneau entre les
    deux ellipses du haut."""
    pts = base.points
    inside = (outer.radial(pts) < 1) & (inner.radial(pts) > 1)
    if not inside.any():
        return 0.0
    depth = np.minimum(outer.distance(pts[inside]), inner.distance(pts[inside]))
    return float(depth.max())


def _gap(e: Ellipse, is_base: bool, outer: Ellipse) -> float:
    """Plus grand arc non tracé ; pour la base, la partie cachée par le haut
    du seau (dans l'ellipse externe) n'est pas un intervalle."""
    a = np.sort(e.angles(e.points))
    if len(a) < 2:
        return e.perimeter
    steps = np.diff(np.append(a, a[0] + 2 * np.pi))
    worst = 0.0
    for start, step in zip(a, steps):
        if is_base:
            middle = e.at(np.array([start + step / 2]))
            if outer.radial(middle)[0] < 1.1 or middle[0, 1] < e.center[1]:
                continue
        worst = max(worst, step / (2 * np.pi) * e.perimeter)
    return float(worst)


def _overlap(a: Ellipse, b: Ellipse) -> float:
    """Diamètre (mm) du plus grand cercle qui tient dans la zone commune."""
    points = np.vstack([a.at(np.linspace(0, 2 * np.pi, 90)), b.at(np.linspace(0, 2 * np.pi, 90))])
    origin = points.min(axis=0) - 1
    size = points.max(axis=0) - origin + 1
    shape = (int(size[1] * RASTER_PX_PER_MM) + 1, int(size[0] * RASTER_PX_PER_MM) + 1)
    masks = []
    for e in (a, b):
        m = np.zeros(shape, np.uint8)
        pts = np.round((e.at(np.linspace(0, 2 * np.pi, 180)) - origin) * RASTER_PX_PER_MM)
        cv2.fillPoly(m, [pts.astype(np.int32)], 1)
        masks.append(m)
    lens = (masks[0] & masks[1]).astype(np.uint8)
    if not lens.any():
        return 0.0
    dist = cv2.distanceTransform(np.pad(lens, 1), cv2.DIST_L2, 5)
    return float(2 * dist.max() / RASTER_PX_PER_MM)


def _away(drawing: Drawing, used: np.ndarray) -> float:
    """Longueur (mm) de traits loin des ellipses et des verticales."""
    total = 0.0
    for stroke in drawing.strokes:
        d = np.sqrt(((stroke.points[:, None, :] - used[None, :, :]) ** 2).sum(-1)).min(1)
        total += float((d > ON_FIGURE_MM).sum()) * STEP_MM
    return total
