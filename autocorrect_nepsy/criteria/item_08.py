"""Item 8 : trois cercles superposés verticalement.

Seuils repris du manuel NEPSY-II (Copie de figures), reformulés.
"""

from __future__ import annotations

import cv2
import numpy as np

from .. import geometry as geo
from ..strokes import Drawing
from . import marks as mk
from .base import ItemResult, Scoring, fmt, fmt_ratio, manual_thresholds
from .shapes import (STRAIGHT_MARGIN_MM, CircleMetrics, circle_metrics, circular_strokes,
                     filled_mask)

# Seuils du manuel, reformulés (liste : autocorrect-nepsy seuils).
threshold = manual_thresholds(__name__)
GENERAL_MAX_RATIO = threshold(2.0, "G", "rapport du grand diamètre d'un cercle au petit diamètre "
                              "d'un autre, au plus", "ratio")
GAP_MM = threshold(5.0, "B", "intervalle ou dépassement d'un cercle qui compte (un seul admis)")
MIN_OVERLAP_MM = threshold(5.0, "D", "chevauchement de deux cercles voisins (cercle grisé), "
                           "au moins")
LOCAL_MAX_CROSS_RATIO = threshold(3.0, "E", "rapport du grand diamètre d'un cercle au petit "
                                  "diamètre d'un autre, au plus", "ratio")
LOCAL_MAX_DIAMETER_MM = threshold(35.0, "F", "plus grand diamètre, au plus")
LOCAL_MAX_OWN_RATIO = threshold(1.5, "F", "rapport des diamètres d'un même cercle, au plus",
                                "ratio")
# Réglages de l'outil (reconnaissance des figures, tolérances de mesure).
DISTORTION_MAX_RATIO = 2.0  # au-delà, le cercle est jugé déformé
DISTORTION_MAX_SPREAD = 0.25  # irrégularité du rayon (bosses, renflements)
RASTER_PX_PER_MM = 8.0  # résolution des calculs de recouvrement
TOUCH_MM = 0.5  # en dessous, deux contours se touchent


def score(drawing: Drawing, item: int = 8) -> ItemResult:
    scoring = Scoring(item, "GABCDEF")
    if drawing.is_empty:
        return scoring.empty()
    circles = circular_strokes(drawing)
    metrics = [circle_metrics(c, drawing.stroke_width) for c in circles]
    scoring.marks += [mk.segment(*m.long_ends, f"Ø {fmt(m.long_diameter)}") for m in metrics]
    scoring.measures["nombre_cercles"] = len(circles)

    for i, m in enumerate(metrics, start=1):
        scoring["A"].limit(m.longest_straight, f"cercle {i} : section droite "
                           f"{fmt(m.longest_straight)} < petit diamètre {fmt(m.short_diameter)} "
                           "(marge de mesure 1 mm)", high=m.short_diameter - STRAIGHT_MARGIN_MM)
    if not metrics:
        scoring["A"].fail("aucune figure circulaire reconnue")
    open_or_over = sum(max(m.gap, m.overshoot) > GAP_MM for m in metrics)
    scoring["B"].add(bool(metrics) and open_or_over <= 1,
                     f"{open_or_over} cercle(s) avec intervalle ou dépassement de plus de "
                     f"{GAP_MM.text} (1 au plus)")

    if len(circles) < 2:
        reason = f"{len(circles)} figure(s) circulaire(s) reconnue(s), il en faut 3"
        scoring.not_recognized(("G", "C", "D", "E", "F"), reason)
        return scoring.result()

    order = np.argsort([m.center[1] for m in metrics])
    circles = [circles[i] for i in order]
    metrics = [metrics[i] for i in order]
    centers = np.array([m.center for m in metrics])
    _, axis = geo.principal_axis(centers)
    alignment = geo.angle_to_vertical(axis)
    cross_ratio = _cross_ratio(metrics)
    three = len(circles) == 3
    scoring.measures.update({"alignement_deg": alignment, "rapport_diametres_croises": cross_ratio})
    scoring.measures.update({f"cercle{i}_grand_diametre_mm": m.long_diameter
                             for i, m in enumerate(metrics, start=1)})

    origin = drawing.points.min(axis=0) - 2
    size = drawing.points.max(axis=0) - origin + 2
    shape = (int(size[1] * RASTER_PX_PER_MM) + 1, int(size[0] * RASTER_PX_PER_MM) + 1)
    masks = [filled_mask(c, origin, shape, RASTER_PX_PER_MM) for c in circles]
    lenses = [_overlap_circle(masks[i], masks[i + 1]) for i in range(len(masks) - 1)]
    overlaps = [width for width, _ in lenses]
    for width, center in lenses:
        if center is not None:
            scoring.marks.append(mk.cercle(origin + center, width / 2,
                                           f"chevauchement {fmt(width)}"))
    scoring.measures.update({f"chevauchement_{i + 1}_{i + 2}_mm": w for i, w in enumerate(overlaps)})
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

    general = scoring["G"]
    general.add(structure, f"trois cercles alignés verticalement ({structure_text})")
    distorted = [i for i, m in enumerate(metrics, start=1) if _distorted(m)]
    general.add(not distorted, "pas de distorsion majeure" if not distorted
                else f"distorsion du ou des cercle(s) {', '.join(map(str, distorted))}")
    general.limit(cross_ratio, "grand diamètre / petit diamètre d'un autre cercle : "
                  f"{fmt_ratio(cross_ratio)} ≤ {GENERAL_MAX_RATIO.text}", high=GENERAL_MAX_RATIO,
                  unit="ratio")

    scoring["C"].add(structure, f"seulement trois cercles alignés verticalement ({structure_text})")

    for i, width in enumerate(overlaps, start=1):
        scoring["D"].limit(width, f"chevauchement cercles {i}-{i + 1} : {fmt(width)} ≥ "
                           f"{MIN_OVERLAP_MM.text}",
                           low=MIN_OVERLAP_MM)
    if not three:
        scoring["D"].fail("il faut trois cercles")

    scoring["E"].limit(cross_ratio, "grand diamètre / petit diamètre d'un autre cercle : "
                       f"{fmt_ratio(cross_ratio)} ≤ {LOCAL_MAX_CROSS_RATIO.text}",
                       high=LOCAL_MAX_CROSS_RATIO, unit="ratio")

    extras = [s for s in drawing.component_sizes[1:] if s >= 5.0]
    scoring["F"].add(three and not extras, "aucun autre élément" if three and not extras
                     else "éléments en trop ou manquants")
    longest = max(m.long_diameter for m in metrics)
    scoring["F"].limit(longest, f"plus grand diamètre {fmt(longest)} ≤ {LOCAL_MAX_DIAMETER_MM.text}",
                       high=LOCAL_MAX_DIAMETER_MM)
    worst = max(m.ratio for m in metrics)
    scoring["F"].limit(worst, f"rapport des diamètres d'un même cercle {fmt_ratio(worst)} ≤ "
                       f"{LOCAL_MAX_OWN_RATIO.text}",
                       high=LOCAL_MAX_OWN_RATIO, unit="ratio")

    return scoring.result()


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
