"""Item 8 : trois cercles superposés verticalement.

Seuils repris du manuel NEPSY-II (Copie de figures), reformulés.
"""

from __future__ import annotations

import cv2
import numpy as np

from .. import geometry as geo
from ..strokes import Drawing
from . import marks as mk
from .base import Checks, ItemResult, empty_result, fmt, fmt_ratio
from .shapes import (STRAIGHT_MARGIN_MM, CircleMetrics, circle_metrics, circular_strokes,
                     filled_mask)

GENERAL_MAX_RATIO = 2.0  # grand diamètre d'un cercle / petit diamètre d'un autre
DISTORTION_MAX_RATIO = 2.0  # au-delà, le cercle est jugé déformé
DISTORTION_MAX_SPREAD = 0.25  # irrégularité du rayon (bosses, renflements)
GAP_MM = 5.0  # Motricité B : intervalle ou dépassement de plus de 5 mm
MIN_OVERLAP_MM = 5.0  # Global D : chevauchement (cercle grisé de 5 mm)
LOCAL_MAX_CROSS_RATIO = 3.0  # Local E
LOCAL_MAX_DIAMETER_MM = 35.0  # Local F
LOCAL_MAX_OWN_RATIO = 1.5  # Local F
RASTER_PX_PER_MM = 8.0  # résolution des calculs de recouvrement
TOUCH_MM = 0.5  # en dessous, deux contours se touchent


def score(drawing: Drawing, item: int = 8) -> ItemResult:
    codes = ("G", "A", "B", "C", "D", "E", "F")
    if drawing.is_empty:
        return empty_result(item, codes, "aucun tracé dans la zone")
    circles = circular_strokes(drawing)
    metrics = [circle_metrics(c, drawing.stroke_width) for c in circles]
    marks = [mk.segment(*m.long_ends, f"Ø {fmt(m.long_diameter)}") for m in metrics]
    checks = {code: Checks() for code in codes}
    measures: dict[str, float] = {"nombre_cercles": len(circles)}

    for i, m in enumerate(metrics, start=1):
        checks["A"].limit(m.longest_straight, f"cercle {i} : section droite "
                          f"{fmt(m.longest_straight)} < petit diamètre {fmt(m.short_diameter)} "
                          "(marge de mesure 1 mm)", high=m.short_diameter - STRAIGHT_MARGIN_MM)
    if not metrics:
        checks["A"].fail("aucune figure circulaire reconnue")
    open_or_over = sum(max(m.gap, m.overshoot) > GAP_MM for m in metrics)
    checks["B"].add(bool(metrics) and open_or_over <= 1,
                    f"{open_or_over} cercle(s) avec intervalle ou dépassement de plus de 5 mm (1 au plus)")

    if len(circles) < 2:
        reason = f"{len(circles)} figure(s) circulaire(s) reconnue(s), il en faut 3"
        for code in ("G", "C", "D", "E", "F"):
            checks[code].fail(reason)
        return ItemResult(item, {c: checks[c].criterion(c) for c in codes}, measures,
                          marks=marks)

    order = np.argsort([m.center[1] for m in metrics])
    circles = [circles[i] for i in order]
    metrics = [metrics[i] for i in order]
    centers = np.array([m.center for m in metrics])
    _, axis = geo.principal_axis(centers)
    alignment = geo.angle_to_vertical(axis)
    cross_ratio = _cross_ratio(metrics)
    three = len(circles) == 3
    measures.update({"alignement_deg": alignment, "rapport_diametres_croises": cross_ratio})
    measures.update({f"cercle{i}_grand_diametre_mm": m.long_diameter
                     for i, m in enumerate(metrics, start=1)})

    origin = drawing.points.min(axis=0) - 2
    size = drawing.points.max(axis=0) - origin + 2
    shape = (int(size[1] * RASTER_PX_PER_MM) + 1, int(size[0] * RASTER_PX_PER_MM) + 1)
    masks = [filled_mask(c, origin, shape, RASTER_PX_PER_MM) for c in circles]
    lenses = [_overlap_circle(masks[i], masks[i + 1]) for i in range(len(masks) - 1)]
    overlaps = [width for width, _ in lenses]
    for width, center in lenses:
        if center is not None:
            marks.append(mk.cercle(origin + center, width / 2, f"chevauchement {fmt(width)}"))
    measures.update({f"chevauchement_{i + 1}_{i + 2}_mm": w for i, w in enumerate(overlaps)})
    if three:
        neighbours_cut = all(w > 0 for w in overlaps)
        ends_apart = (_overlap_width(masks[0], masks[2]) == 0
                      and _min_distance(circles[0].points, circles[2].points) > TOUCH_MM)
    else:
        neighbours_cut = ends_apart = False
    structure = (three and alignment <= 45 and neighbours_cut and ends_apart)
    structure_text = (f"{len(circles)} cercle(s), alignés à {alignment:.0f}° de la verticale ; "
                      f"cercles voisins qui se coupent : {'oui' if neighbours_cut else 'non'} ; "
                      f"haut et bas séparés : {'oui' if ends_apart else 'non'}")

    general = checks["G"]
    general.add(structure, f"trois cercles alignés verticalement ({structure_text})")
    distorted = [i for i, m in enumerate(metrics, start=1) if _distorted(m)]
    general.add(not distorted, "pas de distorsion majeure" if not distorted
                else f"distorsion du ou des cercle(s) {', '.join(map(str, distorted))}")
    general.limit(cross_ratio, "grand diamètre / petit diamètre d'un autre cercle : "
                  f"{fmt_ratio(cross_ratio)} ≤ 2:1", high=GENERAL_MAX_RATIO, unit="ratio")

    checks["C"].add(structure, f"seulement trois cercles alignés verticalement ({structure_text})")

    for i, width in enumerate(overlaps, start=1):
        checks["D"].limit(width, f"chevauchement cercles {i}-{i + 1} : {fmt(width)} ≥ 5 mm",
                          low=MIN_OVERLAP_MM)
    if not three:
        checks["D"].fail("il faut trois cercles")

    checks["E"].limit(cross_ratio, "grand diamètre / petit diamètre d'un autre cercle : "
                      f"{fmt_ratio(cross_ratio)} ≤ 3:1", high=LOCAL_MAX_CROSS_RATIO, unit="ratio")

    extras = [s for s in drawing.component_sizes[1:] if s >= 5.0]
    checks["F"].add(three and not extras,
                    "aucun autre élément" if three and not extras else "éléments en trop ou manquants")
    longest = max(m.long_diameter for m in metrics)
    checks["F"].limit(longest, f"plus grand diamètre {fmt(longest)} ≤ 35 mm",
                      high=LOCAL_MAX_DIAMETER_MM)
    worst = max(m.ratio for m in metrics)
    checks["F"].limit(worst, f"rapport des diamètres d'un même cercle {fmt_ratio(worst)} ≤ 1,5:1",
                      high=LOCAL_MAX_OWN_RATIO, unit="ratio")

    return ItemResult(item, {c: checks[c].criterion(c) for c in codes}, measures, marks=marks)


def _cross_ratio(metrics: list[CircleMetrics]) -> float:
    """Plus grand rapport entre le grand diamètre d'un cercle et le petit
    diamètre d'un autre cercle."""
    best = 1.0
    for i, a in enumerate(metrics):
        for j, b in enumerate(metrics):
            if i != j:
                best = max(best, a.long_diameter / max(b.short_diameter, 1e-6))
    return best


def _distorted(m: CircleMetrics) -> bool:
    return m.corners > 0 or m.ratio > DISTORTION_MAX_RATIO or m.radius_spread > DISTORTION_MAX_SPREAD


def _overlap_width(a: np.ndarray, b: np.ndarray) -> float:
    """Diamètre (mm) du plus grand cercle qui tient dans la zone commune."""
    return _overlap_circle(a, b)[0]


def _overlap_circle(a: np.ndarray, b: np.ndarray) -> tuple[float, np.ndarray | None]:
    """Plus grand cercle qui tient dans la zone commune : diamètre (mm) et
    centre (mm, dans le repère des masques), comme le cercle grisé du manuel."""
    lens = (a & b).astype(np.uint8)
    if not lens.any():
        return 0.0, None
    dist = cv2.distanceTransform(np.pad(lens, 1), cv2.DIST_L2, 5)[1:-1, 1:-1]
    row, col = np.unravel_index(int(np.argmax(dist)), dist.shape)
    center = np.array([col, row], float) / RASTER_PX_PER_MM
    return float(2 * dist.max() / RASTER_PX_PER_MM), center


def _min_distance(a: np.ndarray, b: np.ndarray) -> float:
    diff = a[:, None, :] - b[None, :, :]
    return float(np.sqrt((diff ** 2).sum(-1)).min())
