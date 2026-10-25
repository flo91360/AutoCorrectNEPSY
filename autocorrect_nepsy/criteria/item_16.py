"""Item 16 : triangles imbriqués.

Seuils repris du manuel NEPSY-II (Copie de figures), reformulés.

Le grand triangle est la silhouette du dessin. Le petit triangle est la
région triangulaire du centre ; ses trois voisines (une par côté) complètent
le triangle moyen, dont les coins sont leurs sommets éloignés. Des lignes
relient les coins du grand triangle à ceux du petit.
"""

from __future__ import annotations

import cv2
import numpy as np

from .. import geometry as geo
from ..strokes import Drawing
from . import marks as mk
from .base import Checks, ItemResult, empty_result, fmt, not_recognized
from .polygons import (EDGE_OFFSET_MM, Polygon, away_from, fit_polygon, raster, regions,
                       silhouette, wavy_changes)
from .shapes import EXTRA_ELEMENT_MM

WOBBLE_MM = 0.8  # amplitude d'une ondulation de la main (Motricité A)
MOTOR_MAX_CHANGES = 3  # Motricité A, sur toute la figure
SHARED_SIDE_MM = 2.5  # côté commun à deux régions voisines
JOIN_MM = 2.0  # Général et Motricité B : intervalle ou dépassement
OUTSIDE_MAX_MM = 2.0  # coins d'un triangle hors du triangle qui le contient
LINK_NEAR_MM = 1.5  # une ligne de liaison passe à moins de cette distance
LINK_MIN_COVER = 0.7  # Global D : part tracée d'une ligne de liaison
BASE_MAX_DEG = 10.0  # Global D : bases du moyen et du petit triangle
APEX_BAND_MM = 4.0  # Global D : sommets alignés dans une barre de 4 mm
REGIONS = 10  # Local E : figures triangulaires dans le grand triangle
EQUILATERAL = 4  # Local E
EQUILATERAL_RANGE = (45.0, 75.0)  # angles d'un triangle « sensiblement équilatéral »
RIGHT_TRIANGLES = 6  # Local F
RIGHT_RANGE = (75.0, 105.0)  # Local F : angle droit
ON_FIGURE_MM = 2.0  # encre plus éloignée des régions : autre élément
MIN_BIG_SIDE_FRACTION = 0.4  # grand triangle : côtés de longueurs comparables


def score(drawing: Drawing, item: int = 16) -> ItemResult:
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

    def fail(reason: str, *failing: str) -> ItemResult:
        not_recognized(checks, failing, reason, notes)
        return result()

    outline = silhouette(drawing)
    big, curved = _big_triangle(outline) if outline is not None else (None, False)
    if curved:
        notes.append("côtés du grand triangle très courbes : ses coins sont pris sur le "
                     "triangle qui englobe le dessin, vérifier la cotation")
    closed = regions(drawing)
    triangles = [t for t in (fit_polygon(o, 3) for o in closed) if t is not None]
    changes = _direction_changes(triangles)
    checks["A"].add(changes <= MOTOR_MAX_CHANGES, f"{changes} changement(s) de direction sur "
                    "toute la figure (3 au plus)")
    _count_regions(checks, measures, closed, triangles)
    if big is None:
        return fail("grand triangle non reconnu", "G", "B", "C", "D")
    a, bl, br = _apex_first(big)
    found = _small_and_medium(triangles, big.mean(axis=0))
    if found is None:
        return fail("petit et moyen triangles non reconnus au centre", "G", "B", "C", "D")
    small, medium = found
    s1, s2, s3 = _apex_first(small)
    m3, m1, m2 = _apex_first(medium, top=False)
    measures.update({"base_moyen_deg": geo.angle_to_horizontal(m2 - m1),
                     "base_petit_deg": geo.angle_to_horizontal(s3 - s2)})

    marks.append(mk.trace(np.vstack([big, big[:1]]), "grand", 0))
    marks.append(mk.trace(np.vstack([medium, medium[:1]]), "moyen", 1))
    marks.append(mk.trace(np.vstack([small, small[:1]]), "petit", 2))

    # Coins de chaque triangle par rapport au triangle qui le contient
    # (positif : dehors ; négatif : n'atteint pas le côté).
    medium_out = [_outside(p, big) for p in (m1, m2, m3)]
    small_out = [_outside(p, medium) for p in (s1, s2, s3)]
    links = [_link(drawing, corner, end) for corner, end in ((a, s1), (bl, s2), (br, s3))]
    for (corner, end), (cover, gap) in zip(((a, s1), (bl, s2), (br, s3)), links):
        marks.append(mk.segment(corner, end, f"liaison {cover * 100:.0f} %"))
    redrawn = raster(drawing)
    joints = ([abs(v) for v in medium_out + small_out] + [gap for _, gap in links]
              + (redrawn.gaps if redrawn is not None else []))
    worst = max(joints)
    measures["jonction_max_mm"] = worst

    orientation = (m3[1] > max(m1[1], m2[1]) and s1[1] < min(s2[1], s3[1])
                   and a[1] < min(bl[1], br[1]))
    orientation_text = ("base du moyen en haut, bases du grand et du petit en bas" if orientation
                        else "orientation des triangles différente du modèle")
    inside = max(medium_out) <= OUTSIDE_MAX_MM and max(small_out) <= OUTSIDE_MAX_MM
    inside_text = (f"coins du moyen à {fmt(max(max(medium_out), 0.0))} au plus hors du grand, du "
                   f"petit à {fmt(max(max(small_out), 0.0))} au plus hors du moyen (≤ 2 mm)")
    linked = all(cover >= 0.95 for cover, _ in links)

    general = checks["G"]
    general.add(True, "grand, moyen et petit triangles")
    general.add(orientation, orientation_text)
    general.add(inside, inside_text)
    general.add(linked, "chaque coin du grand triangle relié au coin du petit"
                f" ({', '.join(f'{c * 100:.0f} %' for c, _ in links)} tracés)")
    link_gap = max(gap for _, gap in links)
    general.limit(link_gap, f"plus grand intervalle sur les lignes de liaison {fmt(link_gap)} "
                  "≤ 2 mm", high=JOIN_MM)

    checks["B"].limit(worst, f"plus grand intervalle ou dépassement aux intersections "
                      f"{fmt(worst)} ≤ 2 mm", high=JOIN_MM)

    checks["C"].add(True, "grand, moyen et petit triangles")
    checks["C"].add(orientation, orientation_text)
    checks["C"].add(inside, inside_text)

    checks["D"].add(all(cover >= LINK_MIN_COVER for cover, _ in links),
                    "une ligne relie chaque coin du grand triangle au coin du petit")
    for name, angle in (("moyen", measures["base_moyen_deg"]), ("petit", measures["base_petit_deg"])):
        checks["D"].limit(angle, f"base du triangle {name} à {angle:.0f}° de l'horizontale (≤ 10°)",
                          high=BASE_MAX_DEG, unit="deg")
    spread = float(max(a[0], m3[0], s1[0]) - min(a[0], m3[0], s1[0]))
    measures["alignement_sommets_mm"] = spread
    checks["D"].limit(spread, f"sommets des trois triangles alignés verticalement : écart "
                      f"{fmt(spread)} (barre de 4 mm)", high=APEX_BAND_MM)

    extra = away_from(drawing, closed + [outline], ON_FIGURE_MM)
    extras = int(extra >= EXTRA_ELEMENT_MM) + sum(
        size >= EXTRA_ELEMENT_MM for size in drawing.component_sizes[1:])
    checks["F"].add(extras == 0, "aucun autre élément" if not extras
                    else f"{extras} élément(s) en trop")
    small_angles = _angles(small)
    lo, hi = EQUILATERAL_RANGE
    checks["F"].add(all(lo <= x <= hi for x in small_angles) and linked,
                    f"petit triangle au centre, sensiblement équilatéral (angles "
                    f"{', '.join(f'{x:.0f}°' for x in small_angles)}), relié aux coins du grand")
    return result()


def _count_regions(checks: dict, measures: dict, closed: list, triangles: list[Polygon]) -> None:
    """Local E et F : triangles du découpage, équilatéraux et rectangles."""
    lo, hi = EQUILATERAL_RANGE
    r_lo, r_hi = RIGHT_RANGE
    equilateral = right = 0
    for t in triangles:
        angles = _angles(t.vertices)
        equilateral += all(lo <= x <= hi for x in angles)
        right += any(r_lo <= x <= r_hi for x in angles)
    measures.update({"regions": len(closed), "triangles": len(triangles),
                     "equilateraux": equilateral, "rectangles": right})
    checks["E"].add(len(triangles) == REGIONS and len(closed) == REGIONS,
                    f"{len(triangles)} figure(s) triangulaire(s) sur {len(closed)} région(s) "
                    "(exactement 10)")
    checks["E"].add(equilateral == EQUILATERAL, f"{equilateral} triangle(s) sensiblement "
                    "équilatéral(aux) (exactement 4)")
    checks["F"].add(right == RIGHT_TRIANGLES, f"{right} triangle(s) rectangle(s) (exactement 6)")


def _direction_changes(triangles: list[Polygon]) -> int:
    """Ondulations des lignes, chaque segment entre deux jonctions compté une
    fois (un côté commun à deux régions n'est pas compté deux fois)."""
    seen: list[np.ndarray] = []
    counts = []
    for t in triangles:
        for k in range(3):
            middle = (t.vertices[k] + t.vertices[(k + 1) % 3]) / 2
            if any(np.linalg.norm(middle - m) < SHARED_SIDE_MM for m in seen):
                continue
            seen.append(middle)
            core = t.core(k)
            if len(core) >= 3:
                counts.append(geo.count_direction_changes(core, WOBBLE_MM))
    return wavy_changes(counts)


def _angles(v: np.ndarray) -> list[float]:
    return [geo.angle_between(v[k - 1] - v[k], v[(k + 1) % 3] - v[k]) for k in range(3)]


def _big_triangle(outline: np.ndarray) -> tuple[np.ndarray | None, bool]:
    """Coins du grand triangle : polygone à trois côtés qui suit la silhouette
    ou, si ses côtés sont trop courbes, coins de la silhouette les plus
    proches de ceux du plus petit triangle qui l'englobe (second élément vrai)."""
    fitted = fit_polygon(outline, 3, offset=-EDGE_OFFSET_MM)
    if fitted is not None:
        return fitted.vertices, False
    _, enclosing = cv2.minEnclosingTriangle(outline.astype(np.float32).reshape(-1, 1, 2))
    if enclosing is None:
        return None, False
    corners = [outline[int(np.argmin(np.linalg.norm(outline - t, axis=1)))]
               for t in enclosing.reshape(-1, 2)]
    sides = [np.linalg.norm(corners[k] - corners[(k + 1) % 3]) for k in range(3)]
    if min(sides) < MIN_BIG_SIDE_FRACTION * max(sides):
        return None, False
    return np.array(corners), True


def _apex_first(vertices: np.ndarray, top: bool = True) -> tuple[np.ndarray, ...]:
    """Sommet (le plus haut, ou le plus bas) puis les deux autres de gauche à droite."""
    k = int(np.argmin(vertices[:, 1]) if top else np.argmax(vertices[:, 1]))
    rest = sorted((vertices[i] for i in range(3) if i != k), key=lambda p: p[0])
    return (vertices[k], *rest)


def _small_and_medium(triangles: list[Polygon], center: np.ndarray):
    """Petit triangle (région du centre) et triangle moyen (coins éloignés de
    ses trois voisines, une par côté)."""
    if len(triangles) < 4:
        return None
    small = min(triangles, key=lambda t: _outside(center, t.vertices))
    corners = []
    v = small.vertices
    for k in range(3):
        middle = (v[k] + v[(k + 1) % 3]) / 2
        others = [t for t in triangles if t is not small]
        neighbor = min(others, key=lambda t: np.linalg.norm(t.outline - middle, axis=1).min())
        if np.linalg.norm(neighbor.outline - middle, axis=1).min() > 2.0:
            return None
        far = max(neighbor.vertices, key=lambda p: np.linalg.norm(v - p, axis=1).min())
        corners.append(far)
    return small.vertices, np.array(corners)


def _outside(point: np.ndarray, triangle: np.ndarray) -> float:
    """Distance signée du point au triangle : positive dehors, négative dedans
    (distance au côté le plus proche)."""
    center = triangle.mean(axis=0)
    worst = -np.inf
    for k in range(3):
        a, b = triangle[k], triangle[(k + 1) % 3]
        normal = np.array([-(b - a)[1], (b - a)[0]]) / max(np.linalg.norm(b - a), 1e-9)
        if (center - a) @ normal > 0:
            normal = -normal
        worst = max(worst, float((point - a) @ normal))
    return worst


def _link(drawing: Drawing, start: np.ndarray, end: np.ndarray) -> tuple[float, float]:
    """Part tracée du segment entre deux coins, et plus grand trou le long (mm)."""
    length = float(np.linalg.norm(end - start))
    samples = np.linspace(0, 1, max(2, int(length / 0.5)))
    points = start + np.outer(samples, end - start)
    dist = np.sqrt(((points[:, None, :] - drawing.points[None, :, :]) ** 2).sum(-1)).min(1)
    covered = dist <= LINK_NEAR_MM
    gap = run = 0.0
    step = length / max(len(samples) - 1, 1)
    for ok in covered:
        run = 0.0 if ok else run + step
        gap = max(gap, run)
    return float(covered.mean()), gap
