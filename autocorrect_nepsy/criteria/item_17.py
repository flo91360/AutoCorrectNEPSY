"""Item 17 : figure en V, deux parallélogrammes qui se croisent.

Seuils repris du manuel NEPSY-II (Copie de figures), reformulés.

Les deux parallélogrammes se chevauchent en bas en un triangle ; le reste de
chacun est un trapèze isocèle. On lit les régions fermées du dessin : un
triangle en bas et un trapèze de chaque côté.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .. import geometry as geo
from ..strokes import Drawing
from . import marks as mk
from .base import ItemResult, Scoring, fmt, fmt_ratio, manual_thresholds
from .polygons import (EDGE_OFFSET_MM, Polygon, away_from, corner_polygon, fit_polygon,
                       overshoot, raster, regions, silhouette, turn, wavy_changes)
from .shapes import EXTRA_ELEMENT_MM

# Seuils du manuel, reformulés (liste : autocorrect-nepsy seuils).
threshold = manual_thresholds(__name__)
MOTOR_MAX_CHANGES = threshold(3, "A", "changements de direction sur toute la figure, au plus",
                              "nombre")
JOIN_MM = threshold(2.0, "B", "intervalle ou dépassement aux intersections, au plus")
TOP_MAX_DEG = threshold(20.0, "G", "écart des côtés du haut à l'horizontale, au plus", "deg")
CONVERGENCE_RANGE = (threshold(40.0, "G", "angle de convergence du triangle, au moins", "deg"),
                     threshold(80.0, "G", "angle de convergence du triangle, au plus", "deg"))
GLOBAL_MAX_OUTER_RATIO = threshold(1.2, "C", "rapport des deux lignes extérieures, au plus",
                                   "ratio")
GLOBAL_MAX_BASE_TOP_RATIO = threshold(1.2, "D", "rapport de la base du triangle à chaque côté du "
                                      "haut, au plus", "ratio")
GLOBAL_MIN_OUTER_DEG = threshold(45.0, "D", "angle des lignes extérieures avec l'horizontale, "
                                 "plus de", "deg")
LOCAL_MIN_TRAPEZOID_BASE_MM = threshold(25.0, "E", "grande base de chaque trapèze, au moins")
LOCAL_TRIANGLE_FORBIDDEN = (threshold(75.0, "E", "angle du triangle interdit, à partir de", "deg"),
                            threshold(105.0, "E", "angle du triangle interdit, jusqu'à", "deg"))
LOCAL_MIN_TRIANGLE_SIDE_MM = threshold(15.0, "F", "côté horizontal du triangle, au moins")
LOCAL_MAX_HEIGHT_RATIO = threshold(1.2, "F", "rapport des hauteurs des deux trapèzes, au plus",
                                   "ratio")
# Réglages de l'outil (reconnaissance des figures, tolérances de mesure).
SILHOUETTE_EPSILON_MM = 1.2  # simplification de la silhouette
WOBBLE_MM = 0.8  # amplitude d'une ondulation de la main (Motricité A)
NEAR_RIGHT_DEG = 10.0  # Général : angle « proche de 90° »
PARALLEL_MAX_DEG = 12.0  # côtés parallèles d'un trapèze
ON_OUTLINE_MM = 2.0  # encre plus éloignée des régions : autre élément


@dataclass
class Trapezoid:
    poly: Polygon
    top: tuple[np.ndarray, np.ndarray]  # côté horizontal du haut
    outer: tuple[np.ndarray, np.ndarray]  # grande base (ligne extérieure du V)
    inner: tuple[np.ndarray, np.ndarray]  # petite base, parallèle à la grande

    @property
    def outer_length(self) -> float:
        return float(np.linalg.norm(self.outer[1] - self.outer[0]))

    @property
    def parallel(self) -> float:
        angle = geo.angle_between(self.outer[1] - self.outer[0], self.inner[1] - self.inner[0])
        return min(angle, 180 - angle)

    @property
    def height(self) -> float:
        """Distance entre les deux bases parallèles (milieu de la petite base
        à la droite de la grande)."""
        a, b = self.outer
        d = geo.unit(b - a)
        middle = (self.inner[0] + self.inner[1]) / 2
        return abs(float((middle - a) @ np.array([-d[1], d[0]])))


def score(drawing: Drawing, item: int = 17) -> ItemResult:
    scoring = Scoring(item, "GABCDEF")
    if drawing.is_empty:
        return scoring.empty()

    lines = drawing.significant_lines()
    changes = wavy_changes(line.direction_changes for line in lines)
    scoring["A"].add(changes <= MOTOR_MAX_CHANGES, f"{changes} changement(s) de direction sur "
                     f"toute la figure ({MOTOR_MAX_CHANGES.text} au plus)")

    closed = regions(drawing)
    found = _v_regions(closed)
    if found is None:
        reason = "figure en V non reconnue (un triangle en bas et un trapèze de chaque côté)"
        scoring.not_recognized(("G", "B", "C", "D", "E", "F"), reason)
        return scoring.result()
    triangle, left, right = found
    t = triangle.vertices
    apex = t[int(np.argmin(t[:, 1]))]
    bottom = sorted((p for p in t if not np.array_equal(p, apex)), key=lambda p: p[0])
    base = float(np.linalg.norm(bottom[1] - bottom[0]))
    convergence = geo.angle_between(bottom[0] - apex, bottom[1] - apex)
    triangle_angles = [triangle.angle(k) for k in range(3)]
    tops = [float(np.linalg.norm(z.top[1] - z.top[0])) for z in (left, right)]
    top_angles = [geo.angle_to_horizontal(z.top[1] - z.top[0]) for z in (left, right)]
    outers = [z.outer_length for z in (left, right)]
    outer_angles = [geo.angle_to_horizontal(z.outer[1] - z.outer[0]) for z in (left, right)]
    heights = [z.height for z in (left, right)]
    scoring.measures.update({"base_mm": base, "angle_convergence_deg": convergence,
                             "ligne_exterieure_gauche_mm": outers[0],
                             "ligne_exterieure_droite_mm": outers[1],
                             "haut_gauche_mm": tops[0], "haut_droit_mm": tops[1]})

    for color, poly in enumerate((left.poly, triangle, right.poly)):
        scoring.marks.append(mk.trace(np.vstack([poly.vertices, poly.vertices[:1]]),
                                      ("trapèze", "triangle", "trapèze")[color], color))
    scoring.marks.append(mk.angle(apex, bottom[0], bottom[1], f"{convergence:.0f}°"))
    scoring.marks.append(mk.cote(bottom[0], bottom[1], f"base {fmt(base)}", side=(0.0, 1.0)))
    for z, length, angle in zip((left, right), outers, outer_angles):
        scoring.marks.append(mk.segment(*z.outer, f"{fmt(length)} · {angle:.0f}°"))

    outline = silhouette(drawing)
    r = raster(drawing)
    gaps = r.gaps if r is not None else []
    over = []
    shape = (corner_polygon(outline, SILHOUETTE_EPSILON_MM, -EDGE_OFFSET_MM)
             if outline is not None else None)
    if shape is not None:
        # Les coins rentrants sont les croisements des lignes intérieures : elles
        # s'y prolongent normalement.
        over = [overshoot(drawing, shape, k) for k in range(len(shape.vertices))
                if turn(shape.vertices, k) > 0]
    worst = max(over + gaps + [0.0])
    scoring.measures["jonction_max_mm"] = worst
    scoring["B"].limit(worst, f"plus grand intervalle ou dépassement aux intersections {fmt(worst)} "
                       f"≤ {JOIN_MM.text}", high=JOIN_MM)

    near_right = [a for z in (triangle, left.poly, right.poly)
                  for a in (z.angle(k) for k in range(len(z.vertices)))
                  if abs(a - 90) <= NEAR_RIGHT_DEG]
    lo, hi = CONVERGENCE_RANGE
    general = scoring["G"]
    general.add(True, "V à deux dimensions : un triangle en bas et deux trapèzes")
    for name, angle in zip(("gauche", "droit"), top_angles):
        general.limit(angle, f"côté du haut {name} à {angle:.0f}° de l'horizontale "
                      f"(≤ {TOP_MAX_DEG.text})",
                      high=TOP_MAX_DEG, unit="deg")
    general.add(not near_right, "aucun angle proche de 90°" if not near_right
                else f"{len(near_right)} angle(s) proche(s) de 90° ({_degrees(near_right)})")
    general.limit(convergence, f"angle de convergence {convergence:.0f}° (entre {lo.text} et "
                  f"{hi.text})",
                  low=lo, high=hi, unit="deg")

    outer_ratio = max(outers) / max(min(outers), 1e-6)
    scoring["C"].add(True, "V à deux dimensions")
    scoring["C"].limit(outer_ratio, f"lignes extérieures {fmt(outers[0])} et {fmt(outers[1])} : "
                       f"rapport {fmt_ratio(outer_ratio)} ≤ {GLOBAL_MAX_OUTER_RATIO.text}",
                       high=GLOBAL_MAX_OUTER_RATIO,
                       unit="ratio")

    for name, top in zip(("gauche", "droit"), tops):
        ratio = max(base, top) / max(min(base, top), 1e-6)
        scoring["D"].limit(ratio, f"base {fmt(base)} / haut {name} {fmt(top)} : "
                           f"{fmt_ratio(ratio)} ≤ {GLOBAL_MAX_BASE_TOP_RATIO.text}",
                           high=GLOBAL_MAX_BASE_TOP_RATIO,
                           unit="ratio")
    for name, angle in zip(("gauche", "droite"), outer_angles):
        scoring["D"].limit(angle, f"ligne extérieure {name} à {angle:.0f}° de l'horizontale "
                           f"(> {GLOBAL_MIN_OUTER_DEG.text})", low=GLOBAL_MIN_OUTER_DEG, unit="deg")

    isosceles = [_isosceles(z) for z in (left, right)]
    scoring["E"].add(all(ok for ok, _ in isosceles), "triangle et deux trapèzes isocèles ("
                     + " ; ".join(text for _, text in isosceles) + ")")
    for name, length in zip(("gauche", "droit"), outers):
        scoring["E"].limit(length, f"grande base du trapèze {name} {fmt(length)} ≥ "
                           f"{LOCAL_MIN_TRAPEZOID_BASE_MM.text}",
                           low=LOCAL_MIN_TRAPEZOID_BASE_MM)
    lo, hi = LOCAL_TRIANGLE_FORBIDDEN
    forbidden = [a for a in triangle_angles if lo <= a <= hi]
    scoring["E"].add(not forbidden, f"angles du triangle {_degrees(triangle_angles)} : aucun "
                     f"entre {lo.text} et {hi.text}")

    extra = away_from(drawing, closed + ([outline] if outline is not None else []), ON_OUTLINE_MM)
    extras = int(extra >= EXTRA_ELEMENT_MM) + sum(
        size >= EXTRA_ELEMENT_MM for size in drawing.component_sizes[1:])
    scoring["F"].add(extras == 0, "aucun autre élément" if not extras
                     else f"{extras} élément(s) en trop")
    scoring["F"].limit(base, f"côté horizontal du triangle {fmt(base)} ≥ "
                       f"{LOCAL_MIN_TRIANGLE_SIDE_MM.text}", low=LOCAL_MIN_TRIANGLE_SIDE_MM)
    height_ratio = max(heights) / max(min(heights), 1e-6)
    scoring.measures["rapport_hauteurs_trapezes"] = height_ratio
    scoring["F"].limit(height_ratio, f"hauteurs des trapèzes {fmt(heights[0])} et "
                       f"{fmt(heights[1])} : rapport {fmt_ratio(height_ratio)} ≤ "
                       f"{LOCAL_MAX_HEIGHT_RATIO.text}",
                       high=LOCAL_MAX_HEIGHT_RATIO, unit="ratio")
    return scoring.result()


def _v_regions(found: list[np.ndarray]):
    """Triangle du bas et trapèzes gauche et droit parmi les régions fermées."""
    triangles = [p for p in (fit_polygon(o, 3) for o in found) if p is not None]
    quads = [p for p in (fit_polygon(o, 4) for o in found) if p is not None]
    if not triangles or len(quads) < 2:
        return None
    triangle = max(triangles, key=lambda p: p.vertices[:, 1].mean())
    center = triangle.vertices.mean(axis=0)
    left = [q for q in quads if q.vertices[:, 0].mean() < center[0]]
    right = [q for q in quads if q.vertices[:, 0].mean() >= center[0]]
    if not left or not right:
        return None
    left, right = (max(qs, key=lambda q: abs(_area(q.vertices))) for qs in (left, right))
    return triangle, _trapezoid(left, center), _trapezoid(right, center)


def _area(v: np.ndarray) -> float:
    x, y = v[:, 0], v[:, 1]
    return float(np.dot(x, np.roll(y, -1)) - np.dot(np.roll(x, -1), y)) / 2


def _trapezoid(poly: Polygon, center: np.ndarray) -> Trapezoid:
    """Côtés du trapèze : le haut (le plus horizontal, en haut), la grande base
    (le plus long côté oblique) et la petite base (le côté opposé)."""
    v = poly.vertices
    sides = [(v[k], v[(k + 1) % 4]) for k in range(4)]
    top = min(sides, key=lambda s: (geo.angle_to_horizontal(s[1] - s[0]) > 30,
                                    (s[0][1] + s[1][1]) / 2))
    k = next(i for i, s in enumerate(sides) if s is top)
    slanted = [sides[(k + 1) % 4], sides[(k + 3) % 4]]
    outer = max(slanted, key=lambda s: np.linalg.norm(s[1] - s[0]))
    inner = slanted[1] if outer is slanted[0] else slanted[0]
    return Trapezoid(poly, top, outer, inner)


def _isosceles(z: Trapezoid) -> tuple[bool, str]:
    """Bases parallèles et côtés non parallèles de même longueur, sans angle droit."""
    v = z.poly.vertices
    sides = [(v[k], v[(k + 1) % 4]) for k in range(4)]
    legs = [np.linalg.norm(s[1] - s[0]) for s in sides
            if not any(np.array_equal(s[0], e) and np.array_equal(s[1], f)
                       for e, f in (z.outer, z.inner))]
    legs_ratio = max(legs) / max(min(legs), 1e-6) if len(legs) == 2 else float("inf")
    angles = [z.poly.angle(k) for k in range(4)]
    ok = (z.parallel <= PARALLEL_MAX_DEG and legs_ratio <= 1.5
          and not any(abs(a - 90) <= NEAR_RIGHT_DEG for a in angles))
    return ok, (f"bases à {z.parallel:.0f}° l'une de l'autre, côtés {fmt_ratio(legs_ratio)}, "
                f"angles {_degrees(angles)}")


def _degrees(values: list[float]) -> str:
    return ", ".join(f"{a:.0f}°" for a in values)
