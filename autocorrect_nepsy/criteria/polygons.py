"""Figures fermées faites de côtés droits : silhouette, régions, polygones.

Les traits (lignes médianes) sont redessinés sur une image fine, les petites
interruptions recousues. On en tire la silhouette remplie de la figure (son
contour extérieur, sans les petits dépassements) et les régions fermées
qu'elle délimite (triangles, trapèzes…), simplifiées en polygones.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from .. import geometry as geo
from ..strokes import STEP_MM, Drawing

GAP_MM = 3.0  # interruption recousue pour retrouver une figure fermée
MIN_GAP_MM = 0.3  # plus court, le vide entre deux traits n'est pas une interruption
PX_PER_MM = 8.0
OPENING_MM = 0.8  # petits dépassements et fentes effacés de la silhouette
MIN_REGION_MM2 = 6.0  # plus petite région fermée prise en compte
SIDE_TRIM_MM = 1.5  # bouts d'un côté écartés pour ajuster sa droite
MAX_CORNER_SHIFT_MM = 6.0  # coin recalculé trop loin du contour : on garde le sommet
ROUNDED_MM = 1.2  # coin arrondi : le contour passe loin du coin des deux côtés
# Le contour d'une région longe le bord intérieur du trait redessiné, celui de
# la silhouette son bord extérieur : à cette distance du milieu du trait.
EDGE_OFFSET_MM = 1.5 / PX_PER_MM
SHORT_SIDE_FRACTION = 0.4  # côté plus court : coin mal fermé, fusionné
WEDGE_TOLERANCE_MM = 0.3  # encre au-delà d'un coin : dépassement


@dataclass
class Raster:
    mask: np.ndarray  # traits redessinés (1), fond (0)
    origin: np.ndarray  # coin (mm) du pixel (0, 0)
    gaps: list[float]  # interruptions recousues (mm)

    def to_mm(self, contour: np.ndarray) -> np.ndarray:
        return contour.reshape(-1, 2).astype(float) / PX_PER_MM + self.origin


def raster(drawing: Drawing) -> Raster | None:
    """Traits redessinés (milieu du trait), interruptions de moins de 3 mm recousues."""
    strokes = [st for st in drawing.strokes if len(st.points) >= 2]
    if not strokes:
        return None
    origin = drawing.points.min(axis=0) - 3.0
    size = drawing.points.max(axis=0) - origin + 3.0
    mask = np.zeros((int(size[1] * PX_PER_MM) + 1, int(size[0] * PX_PER_MM) + 1), np.uint8)

    def px(points: np.ndarray) -> np.ndarray:
        return np.round((np.atleast_2d(points) - origin) * PX_PER_MM).astype(np.int32)

    for stroke in strokes:
        cv2.polylines(mask, [px(stroke.points)], stroke.closed, 1, 2)
    gaps = []

    def bridge(a: np.ndarray, b: np.ndarray) -> None:
        cv2.line(mask, tuple(px(a)[0]), tuple(px(b)[0]), 1, 2)
        # Seule la partie du pont hors de l'encre est une interruption (à un
        # coin aigu, les lignes médianes s'arrêtent avant la pointe dessinée).
        samples = a + np.outer(np.linspace(0, 1, max(2, int(np.linalg.norm(b - a) / 0.1))), b - a)
        blank = ~drawing.on_ink(samples)
        run = longest = 0
        for empty in blank:
            run = run + 1 if empty else 0
            longest = max(longest, run)
        length = longest * float(np.linalg.norm(b - a)) / max(len(samples) - 1, 1)
        if length > MIN_GAP_MM:
            gaps.append(length)

    # Chaque bout de trait est relié au point d'encre le plus proche (d'un
    # autre trait, ou du même trait plus loin) s'il est à moins de 3 mm.
    for k, stroke in enumerate(strokes):
        if stroke.closed:
            continue
        for end, own in ((stroke.points[0], stroke.points[10:]),
                         (stroke.points[-1], stroke.points[:-10])):
            others = np.vstack([st.points for j, st in enumerate(strokes) if j != k] + [own])
            if not len(others):
                continue
            dist = np.linalg.norm(others - end, axis=1)
            i = int(np.argmin(dist))
            if 0.3 < dist[i] <= GAP_MM:
                bridge(end, others[i])
    # Deux traits qui se frôlent sans se toucher (un côté qui passe tout près
    # d'un sommet et le dépasse) sont reliés là où ils sont le plus proches.
    for k in range(len(strokes)):
        for j in range(k + 1, len(strokes)):
            a, b = strokes[k].points, strokes[j].points
            dist = np.sqrt(((a[:, None, :] - b[None, :, :]) ** 2).sum(-1))
            i, m = np.unravel_index(int(np.argmin(dist)), dist.shape)
            if 0.3 < dist[i, m] <= GAP_MM:
                bridge(a[i], b[m])
    return Raster(mask, origin, gaps)


def _opened(mask: np.ndarray) -> np.ndarray:
    radius = max(1, int(round(OPENING_MM * PX_PER_MM)))
    disk = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * radius + 1, 2 * radius + 1))
    return cv2.morphologyEx(mask, cv2.MORPH_OPEN, disk)


def _clockwise(outline: np.ndarray) -> np.ndarray:
    """Contour parcouru dans le sens des aiguilles d'une montre à l'écran."""
    return outline if signed_area(outline) > 0 else outline[::-1]


def silhouette(drawing: Drawing) -> np.ndarray | None:
    """Contour extérieur (mm) de la plus grande figure fermée, intérieur rempli,
    petits dépassements et fentes effacés."""
    r = raster(drawing)
    if r is None:
        return None
    flood = np.pad(r.mask.copy(), 1)
    cv2.floodFill(flood, None, (0, 0), 2)
    filled = (flood[1:-1, 1:-1] != 2).astype(np.uint8)
    contours, _ = cv2.findContours(_opened(filled), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not contours:
        return None
    return _clockwise(r.to_mm(max(contours, key=cv2.contourArea)))


def regions(drawing: Drawing) -> list[np.ndarray]:
    """Contours (mm) des régions fermées délimitées par les traits."""
    r = raster(drawing)
    if r is None:
        return []
    count, labels = cv2.connectedComponents((r.mask == 0).astype(np.uint8), connectivity=4)
    border = set(np.unique(np.concatenate([labels[0], labels[-1], labels[:, 0], labels[:, -1]])))
    found = []
    for label in range(1, count):
        if label in border:
            continue
        region = _opened((labels == label).astype(np.uint8))
        if region.sum() < MIN_REGION_MM2 * PX_PER_MM ** 2:
            continue
        contours, _ = cv2.findContours(region, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        if contours:
            found.append(_clockwise(r.to_mm(max(contours, key=cv2.contourArea))))
    return found


def signed_area(points: np.ndarray) -> float:
    """Aire signée (positive dans le sens des aiguilles d'une montre à l'écran)."""
    x, y = points[:, 0], points[:, 1]
    return float(np.dot(x, np.roll(y, -1)) - np.dot(np.roll(x, -1), y)) / 2


def turn(poly: np.ndarray, i: int) -> float:
    """Sens du virage au sommet ``i`` (positif : coin saillant)."""
    a, b, c = poly[i - 1], poly[i], poly[(i + 1) % len(poly)]
    u, v = b - a, c - b
    return float(u[0] * v[1] - u[1] * v[0])


def simplify(outline: np.ndarray, epsilon: float, min_side: float = 0.0) -> np.ndarray:
    """Indices (dans le contour, croissants) des sommets du polygone simplifié ;
    un sommet à moins de ``min_side`` mm du précédent est écarté."""
    poly = cv2.approxPolyDP(outline.astype(np.float32).reshape(-1, 1, 2), epsilon, True)
    poly = poly.reshape(-1, 2).astype(float)
    corners = sorted(int(np.argmin(np.linalg.norm(outline - v, axis=1))) for v in poly)
    kept: list[int] = []
    for c in corners:
        if not kept or np.linalg.norm(outline[c] - outline[kept[-1]]) >= min_side:
            kept.append(c)
    if len(kept) > 1 and np.linalg.norm(outline[kept[0]] - outline[kept[-1]]) < min_side:
        kept.pop()
    return np.array(kept)


@dataclass
class Polygon:
    """Polygone qui suit un contour : coins recalculés à la rencontre des
    côtés ajustés (un coin arrondi ne raccourcit pas les côtés)."""

    outline: np.ndarray
    corners: np.ndarray  # indices des sommets dans le contour
    vertices: np.ndarray  # coins recalculés
    sides: list[np.ndarray]  # points du contour de chaque côté (sommet k → k + 1)

    @property
    def lengths(self) -> list[float]:
        n = len(self.vertices)
        return [float(np.linalg.norm(self.vertices[(k + 1) % n] - self.vertices[k]))
                for k in range(n)]

    def core(self, k: int) -> np.ndarray:
        """Points du côté ``k`` sans ses bouts (le coin, arrondi ou non)."""
        n = len(self.vertices)
        pts = self.sides[k]
        a, b = self.vertices[k], self.vertices[(k + 1) % n]
        keep = np.minimum(np.linalg.norm(pts - a, axis=1), np.linalg.norm(pts - b, axis=1))
        return pts[keep > SIDE_TRIM_MM]

    def angle(self, k: int) -> float:
        """Angle intérieur (degrés) au coin ``k``."""
        n = len(self.vertices)
        a, b, c = self.vertices[k - 1], self.vertices[k], self.vertices[(k + 1) % n]
        inner = geo.angle_between(a - b, c - b)
        return inner if turn(self.vertices, k) >= 0 else 360.0 - inner

    def rounded(self) -> list[tuple[int, float]]:
        """Coins où le contour passe à plus de 1,2 mm du coin recalculé."""
        found = []
        for k in range(len(self.vertices)):
            near = np.vstack([self.sides[k - 1], self.sides[k]])
            gap = float(np.sqrt(((near - self.vertices[k]) ** 2).sum(-1)).min())
            if gap > ROUNDED_MM:
                found.append((k, gap))
        return found


def polygon(outline: np.ndarray, corners: np.ndarray, offset: float = 0.0) -> Polygon:
    """Polygone à partir des sommets ``corners`` du contour ; chaque côté est
    décalé de ``offset`` mm vers l'extérieur (contour d'une région, qui longe
    le bord intérieur du trait) ou vers l'intérieur (``offset`` négatif,
    silhouette qui longe son bord extérieur)."""
    n = len(corners)
    sides = _sides(outline, corners)
    raw = outline[corners]
    lines = []
    for k, pts in enumerate(sides):
        a, b = raw[k], raw[(k + 1) % n]
        keep = np.minimum(np.linalg.norm(pts - a, axis=1), np.linalg.norm(pts - b, axis=1))
        core = pts[keep > SIDE_TRIM_MM]
        center, direction = geo.principal_axis(core if len(core) >= 3 else np.array([a, b]))
        if direction @ (b - a) < 0:
            direction = -direction
        # Sens des aiguilles d'une montre à l'écran : l'extérieur est à gauche.
        lines.append((center + offset * np.array([direction[1], -direction[0]]), direction))
    vertices = raw.copy()
    for k in range(n):
        (c1, d1), (c2, d2) = lines[k - 1], lines[k]
        corner = geo.line_intersection(c1, d1, c2, d2)
        if corner is not None and np.linalg.norm(corner - raw[k]) <= MAX_CORNER_SHIFT_MM:
            vertices[k] = corner
    return Polygon(outline, corners, vertices, _sides(outline, corners))


def _sides(outline: np.ndarray, corners: np.ndarray) -> list[np.ndarray]:
    return [outline[a:b + 1] if a < b else np.vstack([outline[a:], outline[:b + 1]])
            for a, b in zip(corners, np.roll(corners, -1))]


def _to_segment(points: np.ndarray, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    ab = b - a
    t = np.clip(((points - a) @ ab) / max(float(ab @ ab), 1e-9), 0.0, 1.0)
    return np.linalg.norm(points - (a + np.outer(t, ab)), axis=1)


def overshoot(drawing: Drawing, poly: Polygon, k: int, reach: float = 3.0) -> float:
    """Dépassement (mm) au coin ``k`` : encre qui, près du coin, sort de l'angle
    formé par les deux côtés (trait prolongé au-delà du coin). Une autre ligne
    qui arrive au coin par l'intérieur de l'angle n'est pas un dépassement."""
    n = len(poly.vertices)
    a, v, c = poly.vertices[k - 1], poly.vertices[k], poly.vertices[(k + 1) % n]
    points = drawing.points
    near = points[np.linalg.norm(points - v, axis=1) <= reach]
    if not len(near):
        return 0.0
    basis = np.column_stack([geo.unit(a - v), geo.unit(c - v)])
    if abs(np.linalg.det(basis)) < 1e-6:
        return 0.0
    coords = np.linalg.solve(basis, (near - v).T).T  # le long des deux côtés
    beyond = near[(coords < -WEDGE_TOLERANCE_MM).any(axis=1)]
    if not len(beyond):
        return 0.0
    return float(np.minimum(_to_segment(beyond, a, v), _to_segment(beyond, v, c)).max())


def away_from(drawing: Drawing, outlines: list[np.ndarray], distance: float) -> float:
    """Longueur (mm) de traits à plus de ``distance`` des contours : autres éléments."""
    reference = np.vstack(outlines)
    total = 0.0
    for stroke in drawing.strokes:
        d = np.sqrt(((stroke.points[:, None, :] - reference[None, :, :]) ** 2).sum(-1)).min(1)
        total += float((d > distance).sum()) * STEP_MM
    return total


def fit_polygon(outline: np.ndarray, sides: int, epsilons=(1.2, 1.8, 2.4, 3.0),
                offset: float = EDGE_OFFSET_MM) -> Polygon | None:
    """Polygone à ``sides`` côtés qui suit le contour, s'il existe. Un côté
    très court (coin mal fermé) est absorbé par un voisin : on retire celui de
    ses deux sommets dont le retrait change le moins la surface ; les autres
    coins restent à la rencontre de leurs côtés d'origine. On préfère une
    simplification qui donne directement le bon nombre de côtés."""
    for epsilon in epsilons:
        corners = simplify(outline, epsilon)
        if len(corners) == sides:
            return polygon(outline, corners, offset)
    for epsilon in epsilons:
        corners = list(simplify(outline, epsilon))
        if len(corners) < sides:
            continue
        poly = polygon(outline, np.array(corners), offset)
        while len(corners) > sides:
            lengths = poly.lengths
            k = int(np.argmin(lengths))
            if lengths[k] > SHORT_SIDE_FRACTION * max(lengths):
                break
            area = signed_area(poly.vertices)
            n = len(corners)
            drop = min((k, (k + 1) % n), key=lambda i: abs(
                signed_area(np.delete(poly.vertices, i, axis=0)) - area))
            del corners[drop]
            kept = np.array(corners)
            poly = Polygon(outline, kept, np.delete(poly.vertices, drop, axis=0),
                           _sides(outline, kept))
        if len(corners) == sides:
            return poly
    return None


def corner_polygon(outline: np.ndarray, epsilon: float, offset: float = 0.0,
                   min_turn: float = 25.0) -> Polygon | None:
    """Polygone des vrais coins du contour : les sommets où il tourne de moins
    de ``min_turn`` degrés (tremblement d'un côté droit) sont retirés."""
    corners = list(simplify(outline, epsilon))
    while len(corners) >= 3:
        poly = polygon(outline, np.array(corners), offset)
        v, n = poly.vertices, len(corners)
        turns = [geo.angle_between(v[k] - v[k - 1], v[(k + 1) % n] - v[k]) for k in range(n)]
        k = int(np.argmin(turns))
        if turns[k] >= min_turn:
            return poly
        del corners[k]
    return None


def wavy_changes(counts) -> int:
    """Changements de direction à additionner sur toute la figure : seulement
    ceux des lignes qui paraissent ondulées (au moins deux changements) ; une
    ligne simplement arquée n'est pas ondulée."""
    return sum(c for c in counts if c >= 2)
