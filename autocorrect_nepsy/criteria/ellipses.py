"""Ellipses et cercles retrouvés parmi les traits (seau, roues).

Quand plusieurs ellipses se croisent ou que d'autres lignes les rejoignent,
les traits reconstruits passent de l'une à l'autre. On ajuste donc des
ellipses sur des portions de traits prises au hasard (tirage reproductible),
on garde celle que le dessin suit sur la plus grande part de son contour,
on retire ses points et on recommence.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from .. import geometry as geo
from ..strokes import STEP_MM, Drawing

TOLERANCE_MM = 1.2  # un point est sur l'ellipse à moins de cette distance (main levée)
TRIALS = 400  # portions de traits essayées pour chaque ellipse
WINDOW_MM = (12.0, 60.0)  # longueur des portions de traits essayées
MIN_COVERAGE = 0.5  # part du contour tracée pour retenir une ellipse
MIN_AXIS_MM = 4.0
MAX_ELONGATION = 4.0  # au-delà, ce n'est plus une ellipse mais un trait
RUN_GAP_MM = 2.0  # trou qui sépare deux tronçons tracés d'une ellipse
STRAIGHT_TOLERANCE_MM = 0.3  # écart à la corde d'une portion « droite »
CURVED_SAGITTA_MM = 0.6  # flèche de l'ellipse sur la même corde : elle se courbe


@dataclass
class Ellipse:
    center: np.ndarray
    major: float  # grand diamètre (mm)
    minor: float  # petit diamètre (mm)
    major_axis: np.ndarray  # direction du grand axe (vecteur unitaire)
    points: np.ndarray  # points du dessin sur l'ellipse
    coverage: float  # part du contour tracée

    @property
    def minor_axis(self) -> np.ndarray:
        return np.array([-self.major_axis[1], self.major_axis[0]])

    @property
    def ratio(self) -> float:
        return self.major / max(self.minor, 1e-6)

    @property
    def perimeter(self) -> float:
        a, b = self.major / 2, self.minor / 2
        return float(np.pi * (3 * (a + b) - np.sqrt((3 * a + b) * (a + 3 * b))))

    def local(self, points: np.ndarray) -> np.ndarray:
        """Coordonnées réduites (cercle unité) des points."""
        rel = np.atleast_2d(points) - self.center
        return np.column_stack([(rel @ self.major_axis) / (self.major / 2),
                                (rel @ self.minor_axis) / (self.minor / 2)])

    def radial(self, points: np.ndarray) -> np.ndarray:
        """Rayon réduit : 1 sur l'ellipse, moins de 1 dedans."""
        return np.linalg.norm(self.local(points), axis=1)

    def distance(self, points: np.ndarray) -> np.ndarray:
        """Distance approchée (mm) des points au contour de l'ellipse."""
        q = self.local(points)
        r = np.maximum(np.linalg.norm(q, axis=1), 1e-9)
        # Rayon de l'ellipse dans la direction de chaque point.
        reach = np.linalg.norm(self.at(np.arctan2(q[:, 1], q[:, 0])) - self.center, axis=1)
        return np.abs(r - 1) * reach

    def at(self, angles: np.ndarray) -> np.ndarray:
        """Points du contour aux angles (réduits) donnés."""
        angles = np.atleast_1d(angles)
        return (self.center + np.outer(np.cos(angles) * self.major / 2, self.major_axis)
                + np.outer(np.sin(angles) * self.minor / 2, self.minor_axis))

    def angles(self, points: np.ndarray) -> np.ndarray:
        q = self.local(points)
        return np.arctan2(q[:, 1], q[:, 0])

    def largest_gap(self) -> tuple[float, float]:
        """Plus grand arc non tracé : longueur (mm) et angle (réduit) de son milieu."""
        a = np.sort(self.angles(self.points))
        if len(a) < 2:
            return self.perimeter, 0.0
        steps = np.diff(np.append(a, a[0] + 2 * np.pi))
        k = int(np.argmax(steps))
        return float(steps[k] / (2 * np.pi) * self.perimeter), float(a[k] + steps[k] / 2)

    @property
    def spread(self) -> float:
        """Irrégularité du rayon réduit (bosses, renflements)."""
        return float(np.std(self.radial(self.points)))

    def contains(self, points: np.ndarray) -> np.ndarray:
        return self.radial(points) < 1


def _fit(points: np.ndarray) -> Ellipse | None:
    if len(points) < 6:
        return None
    try:
        (cx, cy), (w, h), angle = cv2.fitEllipse(points.astype(np.float32))
    except cv2.error:
        return None
    major, minor = max(w, h), min(w, h)
    if (not np.isfinite([cx, cy, major, minor]).all() or minor < MIN_AXIS_MM
            or major > MAX_ELONGATION * minor):
        return None
    theta = np.radians(angle + (90 if h > w else 0))
    return Ellipse(np.array([cx, cy]), float(major), float(minor),
                   np.array([np.cos(theta), np.sin(theta)]), points, 0.0)


def _coverage(ellipse: Ellipse, points: np.ndarray) -> float:
    if not len(points):
        return 0.0
    bins = np.floor((ellipse.angles(points) + np.pi) / (2 * np.pi) * 72).astype(int) % 72
    return len(np.unique(bins)) / 72


def find_ellipses(drawing: Drawing, count: int, max_size: float | None = None,
                  seed: int = 0) -> list[Ellipse]:
    """Jusqu'à ``count`` ellipses, de la mieux tracée à la moins bien tracée."""
    strokes = [s.points for s in drawing.strokes if len(s.points) >= 10]
    if not strokes:
        return []
    everything = np.vstack(strokes)
    owner = np.concatenate([np.full(len(s), k) for k, s in enumerate(strokes)])
    free = np.ones(len(everything), bool)
    max_size = max_size or 1.5 * drawing.extent
    rng = np.random.default_rng(seed)
    lengths = np.array([len(s) for s in strokes], float)
    found = []
    for _ in range(count):
        best = None
        for _ in range(TRIALS):
            k = int(rng.choice(len(strokes), p=lengths / lengths.sum()))
            span = int(rng.uniform(*WINDOW_MM) / STEP_MM)
            stroke = strokes[k]
            start = int(rng.integers(0, max(1, len(stroke) - span)))
            index = np.flatnonzero(owner == k)[start:start + span]
            window = everything[index[free[index]]]
            candidate = _fit(window)
            if candidate is None or candidate.major > max_size:
                continue
            for _ in range(2):  # réajustement sur les points proches
                near = free & (candidate.distance(everything) <= TOLERANCE_MM)
                refit = _fit(everything[near])
                if refit is None or refit.major > max_size:
                    break
                candidate = refit
            near = free & (candidate.distance(everything) <= TOLERANCE_MM)
            coverage = _coverage(candidate, everything[near])
            score = coverage ** 2 * candidate.perimeter  # une ellipse bien suivie d'abord
            if best is None or score > best[0]:
                candidate.points, candidate.coverage = everything[near], coverage
                best = (score, candidate, near)
        if best is None or best[1].coverage < MIN_COVERAGE:
            break
        found.append(best[1])
        free &= ~best[2]
    return found


def straightest(ellipse: Ellipse) -> float:
    """Plus longue portion droite (mm) du tracé le long de l'ellipse, sur
    chaque tronçon tracé d'un seul tenant. Une portion ne compte que si
    l'ellipse se courbe nettement sur la même corde (le haut d'une ellipse
    aplatie est presque droit sur le modèle aussi)."""
    order = np.argsort(ellipse.angles(ellipse.points))
    pts = ellipse.points[order]
    if len(pts) < 3:
        return 0.0
    steps = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    cuts = np.flatnonzero(steps > RUN_GAP_MM) + 1
    longest = 0.0
    for run in np.split(pts, cuts):
        if len(run) < 3:
            continue
        vertices = run[geo.rdp(run, STRAIGHT_TOLERANCE_MM)]
        for p, q in zip(vertices, vertices[1:]):
            length = float(np.linalg.norm(q - p))
            if length > longest and _sagitta(ellipse, p, q) >= CURVED_SAGITTA_MM:
                longest = length
    return longest


def _sagitta(ellipse: Ellipse, p: np.ndarray, q: np.ndarray) -> float:
    """Flèche (mm) de l'arc d'ellipse entre les points de ``p`` et ``q``."""
    a, b = ellipse.angles(np.array([p, q]))
    if abs(b - a) > np.pi:
        a, b = (a, b + 2 * np.pi) if b < a else (a + 2 * np.pi, b)
    arc = ellipse.at(np.linspace(a, b, 30))
    u, v = arc[0], arc[-1]
    d = geo.unit(v - u)
    normal = np.array([-d[1], d[0]])
    return float(np.abs((arc - u) @ normal).max())


def crosses(a: Ellipse, b: Ellipse) -> bool:
    """Les deux ellipses se coupent : le contour de ``a`` passe dedans et dehors de ``b``."""
    r = b.radial(a.at(np.linspace(0, 2 * np.pi, 180)))
    return bool((r < 1).any() and (r > 1).any())


def concentric(drawing: Drawing, ellipse: Ellipse, scales=np.linspace(1.05, 1.6, 23),
               exclude: np.ndarray | None = None) -> Ellipse | None:
    """Ellipse de même centre et même orientation que ``ellipse``, agrandie
    ou réduite, la mieux suivie par le tracé (points de ``exclude`` écartés)."""
    points = drawing.points
    if exclude is not None and len(exclude):
        far = np.sqrt(((points[:, None, :] - exclude[None, :, :]) ** 2).sum(-1)).min(1)
        points = points[far > TOLERANCE_MM / 2]
    best = None
    for scale in np.concatenate([scales, 1 / scales]):
        candidate = Ellipse(ellipse.center, ellipse.major * scale, ellipse.minor * scale,
                            ellipse.major_axis, points[:0], 0.0)
        near = points[candidate.distance(points) <= TOLERANCE_MM]
        coverage = _coverage(candidate, near)
        if best is None or coverage > best.coverage:
            candidate.points, candidate.coverage = near, coverage
            best = candidate
    if best is None or best.coverage < MIN_COVERAGE:
        return None
    refit = _fit(best.points)
    if refit is not None and np.linalg.norm(refit.center - ellipse.center) < 0.2 * ellipse.minor:
        near = points[refit.distance(points) <= TOLERANCE_MM]
        refit.points, refit.coverage = near, _coverage(refit, near)
        if refit.coverage >= best.coverage:
            return refit
    return best
