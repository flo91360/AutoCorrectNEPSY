"""Mesures partagées entre items : jonctions de lignes et figures circulaires."""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from .. import geometry as geo
from ..strokes import Drawing, StraightLine, Stroke, split_at_corners
from .base import Checks, fmt

# Longueur minimale (mm) d'un élément en trop pour qu'il compte comme
# « autre élément » (en dessous : bavure, petit crochet en fin de trait).
EXTRA_ELEMENT_MM = 5.0
# Petit crochet en début ou fin de trait : ce n'est pas un angle de la figure.
END_HOOK_MM = 4.0
# Une section droite mesurée perd un peu de longueur aux coins (épaisseur du
# trait) : on la compare aux diamètres avec cette marge.
STRAIGHT_MARGIN_MM = 1.0
# Angle franc dans un contour circulaire (distorsion), au-delà du tremblement.
SHARP_CORNER_DEG = 60.0
# Trait doublé (repassé à côté) sur au moins cette longueur : à vérifier.
DOUBLED_NOTE_MM = 3.0


@dataclass
class EndAtPoint:
    """Position de l'extrémité d'une ligne par rapport à un point de jonction."""

    gap: float  # la ligne s'arrête avant le point (mm)
    overshoot: float  # la ligne dépasse le point (mm)


def end_at(line: StraightLine, point: np.ndarray) -> EndAtPoint:
    """Intervalle ou dépassement d'une ligne censée s'arrêter en ``point``."""
    t = line.position(point)
    if t < line.t0:
        return EndAtPoint(line.t0 - t, 0.0)
    if t > line.t1:
        return EndAtPoint(t - line.t1, 0.0)
    return EndAtPoint(0.0, min(t - line.t0, line.t1 - t))


def check_lines(checks: Checks, lines: list[StraightLine], band_mm: float,
                max_interruptions: int | None = None) -> None:
    """Motricité A : interruptions et rectitude (barre grisée) de chaque ligne."""
    if not lines:
        checks.fail("aucune ligne reconnue")
    band = fmt(band_mm, "").replace(",0", "")
    for line in lines:
        name = f"ligne de {fmt(line.length)}"
        if max_interruptions is not None:
            checks.add(line.interruptions <= max_interruptions,
                       f"{name} : {line.interruptions} interruption(s) ≤ {max_interruptions}")
        checks.limit(line.width, f"{name} droite : bande de {fmt(line.width)} ≤ {band} mm",
                     high=band_mm)


def check_direction_changes(checks: Checks, lines: list[StraightLine], maximum: int) -> None:
    """Motricité B : une ligne ondulée change au plus ``maximum`` fois de direction."""
    if not lines:
        checks.fail("aucune ligne reconnue")
    for line in lines:
        checks.add(line.direction_changes <= maximum,
                   f"ligne de {fmt(line.length)} : {line.direction_changes} changement(s) "
                   f"de direction ≤ {maximum}")


def review_notes(lines: list[StraightLine]) -> list[str]:
    """Situations que les règles tranchent mal : à faire vérifier."""
    notes = []
    for line in lines:
        if line.doubled_length >= DOUBLED_NOTE_MM:
            notes.append(f"ligne de {line.length:.0f} mm repassée à côté du premier tracé "
                         f"sur {line.doubled_length:.0f} mm : vérifier la cotation")
    return notes


def outside(line: StraightLine, point: np.ndarray) -> float:
    """Distance (mm) le long de la ligne entre ``point`` et le tracé, 0 si le
    point se projette sur le tracé."""
    t = line.position(point)
    return max(line.t0 - t, t - line.t1, 0.0)


def intersection(a: StraightLine, b: StraightLine) -> np.ndarray | None:
    return geo.line_intersection(a.center, a.direction, b.center, b.direction)


def extra_elements(drawing: Drawing, used: list[StraightLine]) -> list[float]:
    """Longueurs des éléments du dessin qui n'appartiennent pas à la figure."""
    used_ids = {id(line) for line in used}
    threshold = max(EXTRA_ELEMENT_MM, 0.1 * drawing.extent)
    extras = [line.length for line in drawing.lines
              if id(line) not in used_ids and line.length >= threshold]
    # Morceaux d'encre séparés du dessin principal.
    extras += [size for size in drawing.component_sizes[1:] if size >= threshold]
    return extras


@dataclass
class CircleMetrics:
    center: np.ndarray
    long_diameter: float
    short_diameter: float
    perimeter: float
    gap: float  # longueur du contour non tracée (mm)
    overshoot: float  # longueur tracée deux fois (mm)
    longest_straight: float  # plus longue section droite (mm)
    rounded: bool  # au moins un changement de direction arrondi
    corners: int  # angles marqués (hors extrémités du trait)
    radius_spread: float  # irrégularité du rayon (écart-type / rayon moyen)

    @property
    def ratio(self) -> float:
        return self.long_diameter / max(self.short_diameter, 1e-6)


def circle_metrics(stroke: Stroke, stroke_width: float) -> CircleMetrics:
    points = stroke.points
    long_d = geo.max_diameter(points)
    short_d = geo.min_strip_width(points)
    perimeter = np.pi * (long_d + short_d) / 2
    center = points.mean(axis=0)
    rel = points - center
    angles = np.degrees(np.arctan2(rel[:, 1], rel[:, 0])) % 360
    radii = np.linalg.norm(rel, axis=1)
    bins = (angles // 5).astype(int)
    covered = layered = 0
    for b in range(72):
        r = radii[bins == b]
        if len(r) == 0:
            continue
        covered += 1
        if r.max() - r.min() > 1.0 + stroke_width:
            layered += 1
    gap = (72 - covered) / 72 * perimeter
    overshoot = layered / 72 * perimeter
    closed_pts = np.vstack([points, points[:1]]) if stroke.closed else points
    keep = geo.rdp(closed_pts, 1.0)
    segments = np.linalg.norm(np.diff(closed_pts[keep], axis=0), axis=1)
    longest = float(segments.max()) if len(segments) else 0.0
    return CircleMetrics(
        center, long_d, short_d, perimeter, gap, overshoot, longest,
        rounded=_has_rounded_turn(stroke),
        corners=_inner_corners(stroke),
        radius_spread=float(radii.std() / max(radii.mean(), 1e-6)),
    )


def net_turning(points: np.ndarray) -> float:
    """Rotation totale signée (degrés) le long d'un trait."""
    pts = geo.resample(points, 1.0)
    if len(pts) < 3:
        return 0.0
    d = np.diff(pts, axis=0)
    heading = np.unwrap(np.arctan2(d[:, 1], d[:, 0]))
    return float(np.degrees(heading[-1] - heading[0]))


def _has_rounded_turn(stroke: Stroke) -> bool:
    for piece in split_at_corners(stroke):
        if geo.path_length(piece) >= 5.0 and abs(net_turning(piece)) >= 45.0:
            return True
    return False


def _inner_corners(stroke: Stroke) -> int:
    """Angles francs du trait, sans compter les crochets aux extrémités."""
    pieces = split_at_corners(stroke, SHARP_CORNER_DEG)
    if stroke.closed:
        return len(pieces) if len(pieces) > 1 else 0
    lengths = [geo.path_length(p) for p in pieces]
    inner = 0
    for i in range(len(pieces) - 1):
        hook_at_start = i == 0 and lengths[0] < END_HOOK_MM
        hook_at_end = i + 1 == len(pieces) - 1 and lengths[-1] < END_HOOK_MM
        if not (hook_at_start or hook_at_end):
            inner += 1
    return inner


def circular_strokes(drawing: Drawing, min_turning: float = 240.0) -> list[Stroke]:
    """Traits qui forment une figure circulaire (boucle presque complète)."""
    found = []
    for stroke in drawing.strokes:
        if stroke.length < 5.0:
            continue
        if stroke.closed or abs(net_turning(stroke.points)) >= min_turning:
            found.append(stroke)
    return found


def filled_mask(stroke: Stroke, origin: np.ndarray, shape: tuple[int, int],
                scale: float) -> np.ndarray:
    """Disque plein délimité par un trait fermé (raster à ``scale`` px/mm)."""
    mask = np.zeros(shape, np.uint8)
    pts = np.round((stroke.points - origin) * scale).astype(np.int32)
    cv2.fillPoly(mask, [pts], 1)
    return mask
