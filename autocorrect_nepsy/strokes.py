"""Reconstruction des traits de l'enfant à partir du masque d'encre.

1. Le masque est réduit à son squelette (ligne d'un pixel d'épaisseur).
2. Le squelette devient un graphe : des nœuds (extrémités, croisements) reliés
   par des arêtes (portions de trait sans embranchement).
3. À chaque croisement, on recolle les arêtes qui se prolongent le mieux :
   deux traits qui se croisent en « X » redonnent deux traits continus.
4. Les traits sont découpés aux angles marqués puis les morceaux alignés sont
   regroupés en lignes droites (une ligne peut avoir des interruptions).

Toutes les mesures sont en mm.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from functools import cached_property

import cv2
import numpy as np

from . import geometry as geo

STEP_MM = 0.3  # pas de rééchantillonnage des traits
NODE_RADIUS_MM = 1.2  # rayon de regroupement des pixels de croisement
MIN_COMPONENT_MM = 1.0  # taches plus petites ignorées (poussières, bavures)
CORNER_SCALE_MM = 2.0  # demi-fenêtre de calcul des angles le long d'un trait
CORNER_ANGLE = 35.0  # changement de direction au-delà duquel on coupe le trait
MERGE_ANGLE = 15.0  # écart d'orientation max pour raccorder deux morceaux
MERGE_OFFSET_MM = 2.0  # décalage latéral max pour raccorder deux morceaux
MERGE_GAP_MM = 10.0  # interruption max entre deux morceaux d'une même ligne
INTERRUPTION_MM = 0.5  # vide minimal le long d'une ligne pour une interruption
DOUBLED_SEPARATION_MM = 0.8  # écart à partir duquel deux passages se distinguent

_OFFSETS = [(-1, -1), (-1, 0), (-1, 1), (0, 1), (1, 1), (1, 0), (1, -1), (0, -1)]


@dataclass
class Stroke:
    """Trait continu, points ordonnés le long du tracé."""

    points: np.ndarray
    closed: bool

    @property
    def length(self) -> float:
        return geo.path_length(self.points, self.closed)


@dataclass
class StraightLine:
    """Ligne droite reconstituée, éventuellement en plusieurs morceaux."""

    pieces: list[np.ndarray]
    stroke_width: float
    center: np.ndarray = field(init=False)
    direction: np.ndarray = field(init=False)
    t0: float = field(init=False)
    t1: float = field(init=False)

    def __post_init__(self) -> None:
        self.center, self.direction = geo.principal_axis(self.points)
        t = (self.points - self.center) @ self.direction
        self.t0, self.t1 = float(t.min()), float(t.max())

    @cached_property
    def points(self) -> np.ndarray:
        return np.vstack(self.pieces)

    @property
    def length(self) -> float:
        return self.t1 - self.t0

    @property
    def ends(self) -> tuple[np.ndarray, np.ndarray]:
        return (self.center + self.t0 * self.direction,
                self.center + self.t1 * self.direction)

    def position(self, point: np.ndarray) -> float:
        """Abscisse de la projection d'un point sur l'axe de la ligne."""
        return float((point - self.center) @ self.direction)

    @cached_property
    def interruptions(self) -> int:
        spans = sorted((float(t.min()), float(t.max())) for t in
                       ((piece - self.center) @ self.direction for piece in self.pieces))
        count, reach = 0, spans[0][1]
        for start, end in spans[1:]:
            if start - reach > INTERRUPTION_MM:
                count += 1
            reach = max(reach, end)
        return count

    @cached_property
    def doubled_length(self) -> float:
        """Longueur (mm) sur laquelle deux morceaux de la ligne courent côte à
        côte sans se confondre (trait repassé à côté du premier passage)."""
        normal = np.array([-self.direction[1], self.direction[0]])
        profiles = []
        for piece in self.pieces:
            t = (piece - self.center) @ self.direction
            order = np.argsort(t)
            profiles.append((t[order], ((piece - self.center) @ normal)[order]))
        total = 0.0
        for i, (ti, ni) in enumerate(profiles):
            for tj, nj in profiles[i + 1:]:
                lo, hi = max(ti[0], tj[0]), min(ti[-1], tj[-1])
                if hi - lo < 1.0:
                    continue
                grid = np.linspace(lo, hi, 25)
                apart = np.abs(np.interp(grid, ti, ni) - np.interp(grid, tj, nj))
                total += (hi - lo) * float(np.mean(apart > DOUBLED_SEPARATION_MM))
        return total

    @cached_property
    def width(self) -> float:
        """Largeur de la plus étroite bande contenant le trait (encre comprise)."""
        return geo.min_strip_width(self.points) + self.stroke_width

    @cached_property
    def direction_changes(self) -> int:
        pieces = [piece for piece in self.pieces if len(piece) >= 3]
        return max((geo.count_direction_changes(piece, 0.8) for piece in pieces), default=0)

    def angle_to_horizontal(self) -> float:
        return geo.angle_to_horizontal(self.direction)

    def angle_to_vertical(self) -> float:
        return geo.angle_to_vertical(self.direction)


@dataclass
class Drawing:
    """Dessin de l'enfant pour un item."""

    strokes: list[Stroke]
    stroke_width: float
    component_sizes: list[float]

    @property
    def is_empty(self) -> bool:
        return not self.strokes

    @cached_property
    def points(self) -> np.ndarray:
        if not self.strokes:
            return np.zeros((0, 2))
        return np.vstack([s.points for s in self.strokes])

    @property
    def extent(self) -> float:
        return geo.max_diameter(self.points) if len(self.points) else 0.0

    @cached_property
    def lines(self) -> list[StraightLine]:
        """Lignes droites du dessin, des plus longues aux plus courtes."""
        pieces = [piece for stroke in self.strokes for piece in split_at_corners(stroke)]
        return merge_collinear(pieces, self.stroke_width)

    def significant_lines(self, min_fraction: float = 0.12,
                          min_length: float = 4.0) -> list[StraightLine]:
        threshold = max(min_length, min_fraction * self.extent)
        return [line for line in self.lines if line.length >= threshold]


def extract_drawing(ink: np.ndarray, px_per_mm: float) -> Drawing:
    """Construit le dessin (traits en mm) à partir du masque d'encre d'une zone."""
    mask = _clean(ink, px_per_mm)
    skeleton = skeletonize(mask.astype(bool))
    if not skeleton.any():
        return Drawing([], 0.0, [])
    stroke_width = float(mask.sum() / max(1, skeleton.sum())) / px_per_mm
    graph = _SkeletonGraph(skeleton, px_per_mm)
    strokes = [Stroke(geo.resample(points, STEP_MM, closed), closed)
               for points, closed in graph.strokes()]
    strokes = [s for s in strokes if s.length >= MIN_COMPONENT_MM]
    count, labels = cv2.connectedComponents(mask, connectivity=8)
    sizes = []
    for label in range(1, count):
        ys, xs = np.nonzero(labels == label)
        sizes.append(geo.max_diameter(np.column_stack([xs, ys]).astype(float)) / px_per_mm)
    return Drawing(strokes, stroke_width, sorted(sizes, reverse=True))


def skeletonize(mask: np.ndarray) -> np.ndarray:
    """Amincit le tracé jusqu'à une ligne d'un pixel (algorithme de Guo et Hall)."""
    img = np.pad(mask.astype(bool), 1)
    core = img[1:-1, 1:-1]
    while True:
        changed = False
        for step in (0, 1):
            p2, p3, p4 = img[:-2, 1:-1], img[:-2, 2:], img[1:-1, 2:]
            p5, p6, p7 = img[2:, 2:], img[2:, 1:-1], img[2:, :-2]
            p8, p9 = img[1:-1, :-2], img[:-2, :-2]
            crossings = ((~p2 & (p3 | p4)).astype(np.int8) + (~p4 & (p5 | p6))
                         + (~p6 & (p7 | p8)) + (~p8 & (p9 | p2)))
            n1 = (p9 | p2).astype(np.int8) + (p3 | p4) + (p5 | p6) + (p7 | p8)
            n2 = (p2 | p3).astype(np.int8) + (p4 | p5) + (p6 | p7) + (p8 | p9)
            n = np.minimum(n1, n2)
            if step == 0:
                side = (p6 | p7 | ~p9) & p8
            else:
                side = (p2 | p3 | ~p5) & p4
            remove = core & (crossings == 1) & (n >= 2) & (n <= 3) & ~side
            if remove.any():
                core[remove] = False
                changed = True
        if not changed:
            return core.copy()


def _clean(ink: np.ndarray, px_per_mm: float) -> np.ndarray:
    """Bouche les micro-sauts du stylo et retire les poussières."""
    radius = max(1, int(round(0.25 * px_per_mm)))
    disk = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * radius + 1, 2 * radius + 1))
    mask = cv2.morphologyEx(ink.astype(np.uint8), cv2.MORPH_CLOSE, disk)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    min_size = MIN_COMPONENT_MM * px_per_mm
    for label in range(1, count):
        if max(stats[label, 2], stats[label, 3]) < min_size:
            mask[labels == label] = 0
    return mask


class _SkeletonGraph:
    """Graphe du squelette : nœuds = extrémités et croisements, arêtes = chemins."""

    def __init__(self, skeleton: np.ndarray, px_per_mm: float):
        self.px_per_mm = px_per_mm
        self.edges: list[list] = []  # [points (mm), nœud début, nœud fin]
        self.node_centers: list[np.ndarray] = []
        self._build(skeleton)
        self._prune_spurs()

    # -- construction -------------------------------------------------------
    def _build(self, skeleton: np.ndarray) -> None:
        sk = skeleton.astype(np.uint8)
        padded = np.pad(sk, 1)
        ring = [padded[1 + dr:padded.shape[0] - 1 + dr, 1 + dc:padded.shape[1] - 1 + dc]
                for dr, dc in _OFFSETS]
        # Nombre de passages 0 -> 1 autour du pixel : 1 = extrémité, >= 3 = croisement.
        crossings = sum(((ring[i] == 0) & (ring[(i + 1) % 8] == 1)).astype(np.uint8)
                        for i in range(8))
        neighbors = sum(r.astype(np.uint8) for r in ring)
        # Un croisement en X donne parfois un petit bloc de pixels où le nombre de
        # passages reste à 2 : on le repère alors par son nombre de voisins.
        junction = (sk == 1) & ((crossings >= 3) | (neighbors >= 4))
        radius = max(1, int(round(NODE_RADIUS_MM * self.px_per_mm)))
        disk = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * radius + 1, 2 * radius + 1))
        node_area = cv2.dilate(junction.astype(np.uint8), disk) & sk
        count, node_labels = cv2.connectedComponents(node_area, connectivity=8)
        for label in range(1, count):
            ys, xs = np.nonzero((node_labels == label) & junction)
            if len(xs) == 0:
                ys, xs = np.nonzero(node_labels == label)
            self.node_centers.append(np.array([xs.mean(), ys.mean()]) / self.px_per_mm)
        rest = sk & (node_area == 0)
        count, edge_labels = cv2.connectedComponents(rest, connectivity=8)
        h, w = sk.shape
        for label in range(1, count):
            pixels = np.column_stack(np.nonzero(edge_labels == label))
            path, closed = _order_pixels(pixels)
            ends = []
            for r, c in (path[0], path[-1]):
                node = -1
                for dr, dc in _OFFSETS:
                    rr, cc = r + dr, c + dc
                    if 0 <= rr < h and 0 <= cc < w and node_labels[rr, cc] > 0:
                        node = int(node_labels[rr, cc]) - 1
                        break
                ends.append(node)
            points = path[:, ::-1].astype(float) / self.px_per_mm
            if closed and ends == [-1, -1]:
                self.edges.append([points, None, None])
                continue
            start, end = (self._attach(points, ends[0], at_start=True),
                          self._attach(points, ends[1], at_start=False))
            if ends[0] >= 0:
                points = np.vstack([self.node_centers[ends[0]], points])
            if ends[1] >= 0:
                points = np.vstack([points, self.node_centers[ends[1]]])
            self.edges.append([points, start, end])
        # Nœuds sans arête (croisement isolé dans un amas d'encre) : ignorés.

    def _attach(self, points: np.ndarray, node: int, at_start: bool) -> int:
        if node >= 0:
            return node
        self.node_centers.append(points[0] if at_start else points[-1])
        return len(self.node_centers) - 1

    def _incident(self) -> dict[int, list[tuple[int, int]]]:
        incident: dict[int, list[tuple[int, int]]] = {}
        for index, (_, start, end) in enumerate(self.edges):
            if start is None:
                continue
            incident.setdefault(start, []).append((index, 0))
            incident.setdefault(end, []).append((index, 1))
        return incident

    def _prune_spurs(self) -> None:
        """Retire les petites barbes du squelette dues à l'épaisseur de l'encre."""
        spur = 1.5
        for _ in range(3):
            incident = self._incident()
            remove = set()
            for index, (points, start, end) in enumerate(self.edges):
                if start is None or geo.path_length(points) >= spur:
                    continue
                free_start = len(incident[start]) == 1
                free_end = len(incident[end]) == 1
                if free_start != free_end:
                    remove.add(index)
            if not remove:
                return
            self.edges = [e for i, e in enumerate(self.edges) if i not in remove]

    # -- traits continus ----------------------------------------------------
    def strokes(self) -> list[tuple[np.ndarray, bool]]:
        incident = self._incident()
        partner: dict[tuple[int, int], tuple[int, int]] = {}
        for node, ends in incident.items():
            for a, b in self._pair(node, ends):
                partner[a] = b
                partner[b] = a
        result = []
        visited: set[int] = set()

        def oriented(index: int, from_end: int) -> np.ndarray:
            points = self.edges[index][0]
            return points if from_end == 0 else points[::-1]

        def walk(index: int, from_end: int) -> tuple[list[np.ndarray], bool]:
            chain, start = [], (index, from_end)
            while True:
                visited.add(index)
                chain.append(oriented(index, from_end))
                nxt = partner.get((index, 1 - from_end))
                if nxt is None:
                    return chain, False
                if nxt == start:
                    return chain, True
                if nxt[0] in visited:
                    return chain, False
                index, from_end = nxt

        for index, (points, start, _) in enumerate(self.edges):
            if start is None:
                visited.add(index)
                result.append((points, True))
        # D'abord les traits ouverts, en partant d'une extrémité libre.
        for index in range(len(self.edges)):
            for end in (0, 1):
                if index not in visited and (index, end) not in partner:
                    chain, closed = walk(index, end)
                    result.append((_join(chain), closed))
        # Restent les boucles dont toutes les arêtes sont recollées.
        for index in range(len(self.edges)):
            if index not in visited:
                chain, closed = walk(index, 0)
                result.append((_join(chain), closed))
        return result

    def _pair(self, node: int, ends: list[tuple[int, int]]) -> list[tuple]:
        if len(ends) == 2:
            return [tuple(ends)]
        if len(ends) < 2:
            return []
        center = self.node_centers[node]
        directions = []
        for index, end in ends:
            points = self.edges[index][0]
            points = points if end == 0 else points[::-1]
            directions.append(_direction_from(points, center))
        candidates = []
        for i in range(len(ends)):
            for j in range(i + 1, len(ends)):
                deviation = 180.0 - geo.angle_between(directions[i], directions[j])
                if deviation <= 60.0:
                    candidates.append((deviation, i, j))
        used, pairs = set(), []
        for _, i, j in sorted(candidates):
            if i not in used and j not in used:
                used.update((i, j))
                pairs.append((ends[i], ends[j]))
        return pairs


def _direction_from(points: np.ndarray, center: np.ndarray) -> np.ndarray:
    """Direction de départ d'une arête, mesurée à ~3 mm du nœud."""
    distances = np.linalg.norm(points - center, axis=1)
    reach = min(3.0, 0.6 * float(distances.max()))
    beyond = np.flatnonzero(distances >= reach)
    target = points[beyond[0]] if len(beyond) else points[-1]
    return geo.unit(target - center)


def _join(chain: list[np.ndarray]) -> np.ndarray:
    parts = [chain[0]]
    for part in chain[1:]:
        if len(parts[-1]) and len(part) and np.allclose(parts[-1][-1], part[0]):
            part = part[1:]
        parts.append(part)
    return np.vstack(parts)


def _order_pixels(pixels: np.ndarray) -> tuple[np.ndarray, bool]:
    """Ordonne les pixels d'une arête de squelette. Renvoie (chemin, fermé)."""
    index = {(int(r), int(c)): i for i, (r, c) in enumerate(pixels)}
    neighbors = [[index[(r + dr, c + dc)] for dr, dc in _OFFSETS if (r + dr, c + dc) in index]
                 for r, c in map(tuple, pixels)]
    if len(pixels) == 1:
        return pixels, False
    ends = [i for i, n in enumerate(neighbors) if len(n) <= 1]
    if ends:
        far, _ = _bfs(neighbors, ends[0])
        other, parent = _bfs(neighbors, far)
        return pixels[_unwind(parent, other)], False
    # Boucle fermée : chemin d'un pixel à son voisin sans passer par leur lien direct.
    start, blocked = 0, neighbors[0][0]
    _, parent = _bfs(neighbors, start, forbidden=(start, blocked))
    if blocked not in parent:
        return pixels[[start]], False
    return pixels[_unwind(parent, blocked)], True


def _bfs(neighbors, start, forbidden=None):
    parent = {start: None}
    queue = deque([start])
    last = start
    while queue:
        last = queue.popleft()
        for nxt in neighbors[last]:
            if nxt in parent or (forbidden and {last, nxt} == set(forbidden)):
                continue
            parent[nxt] = last
            queue.append(nxt)
    return last, parent


def _unwind(parent, node) -> list[int]:
    path = []
    while node is not None:
        path.append(node)
        node = parent[node]
    return path[::-1]


def split_at_corners(stroke: Stroke, angle: float = CORNER_ANGLE) -> list[np.ndarray]:
    """Coupe un trait aux changements de direction de plus de ``angle`` degrés."""
    pts = stroke.points
    k = max(2, int(round(CORNER_SCALE_MM / STEP_MM)))
    n = len(pts)
    if n < 2 * k + 1:
        return [pts]
    smooth = geo.smooth(pts, 3, stroke.closed)
    turn = np.zeros(n)
    for i in range(n):
        if stroke.closed:
            a, b, c = smooth[(i - k) % n], smooth[i], smooth[(i + k) % n]
        elif k <= i < n - k:
            a, b, c = smooth[i - k], smooth[i], smooth[i + k]
        else:
            continue
        turn[i] = geo.angle_between(b - a, c - b)
    corners = []
    for i in np.argsort(-turn):
        if turn[i] < angle:
            break
        if all(min(abs(i - j), n - abs(i - j) if stroke.closed else n) > k for j in corners):
            corners.append(int(i))
    corners.sort()
    if not corners:
        return [pts]
    if stroke.closed:
        rolled = np.roll(pts, -corners[0], axis=0)
        cuts = [c - corners[0] for c in corners] + [n]
        return [rolled[a:b + 1] if b < n else np.vstack([rolled[a:], rolled[:1]])
                for a, b in zip(cuts, cuts[1:])]
    cuts = [0] + corners + [n - 1]
    return [pts[a:b + 1] for a, b in zip(cuts, cuts[1:]) if b > a]


def merge_collinear(pieces: list[np.ndarray], stroke_width: float) -> list[StraightLine]:
    """Regroupe les morceaux alignés (interruptions, reprises du tracé)."""
    pieces = [p for p in pieces if len(p) >= 2 and geo.path_length(p) >= 0.6]
    pieces.sort(key=lambda p: -geo.path_length(p))
    groups: list[list[np.ndarray]] = []
    for piece in pieces:
        center, direction = geo.principal_axis(piece)
        merged = False
        for group in groups:
            line = StraightLine(group, stroke_width)
            if geo.angle_between(direction, line.direction) > 90:
                direction = -direction
            if geo.angle_between(direction, line.direction) > MERGE_ANGLE:
                continue
            normal = np.array([-line.direction[1], line.direction[0]])
            if np.abs((piece - line.center) @ normal).mean() > MERGE_OFFSET_MM:
                continue
            t = (piece - line.center) @ line.direction
            gap = max(float(t.min()) - line.t1, line.t0 - float(t.max()), 0.0)
            if gap > MERGE_GAP_MM:
                continue
            group.append(piece)
            merged = True
            break
        if not merged:
            groups.append([piece])
    lines = [StraightLine(group, stroke_width) for group in groups]
    return sorted(lines, key=lambda line: -line.length)
