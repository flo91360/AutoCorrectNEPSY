"""Ellipses et cercles retrouvés parmi les traits (seau, roues).

Quand plusieurs ellipses se croisent ou que d'autres lignes les rejoignent,
les traits reconstruits passent de l'une à l'autre. On ajuste donc des
ellipses sur des portions de traits prises tout le long de chaque trait, à
intervalles réguliers en mm (le résultat ne dépend ni du hasard ni de la
résolution du scan). On garde celle que le dessin suit sur la plus grande part
de son contour, on retire ses points et on recommence. Seuls comptent les
points dont le tracé longe l'ellipse : un rayon qui la traverse n'en trace
pas une portion.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from .. import geometry as geo
from ..strokes import STEP_MM, Drawing

TOLERANCE_MM = 1.2  # un point est sur l'ellipse à moins de cette distance (main levée)
ALIGNED_DEG = 30.0  # le tracé longe l'ellipse : direction à moins de 30° de sa tangente
WINDOW_LENGTHS_MM = (15.0, 25.0, 40.0, 60.0)  # longueur des portions de traits essayées
WINDOW_STEP_MM = 3.0  # écart entre les débuts de deux portions essayées
POLISHED = 5  # ellipses candidates affinées avant d'en retenir une
POLISH_STEPS = ((1.0, 1.0, 4.0), (0.5, 0.5, 2.0), (0.25, 0.25, 1.0))  # centre, axes (mm), angle (°)
MIN_COVERAGE = 0.5  # part du contour tracée pour retenir une ellipse
MIN_AXIS_MM = 4.0
MAX_ELONGATION = 4.0  # au-delà, ce n'est plus une ellipse mais un trait
RUN_GAP_MM = 2.0  # trou qui sépare deux tronçons tracés d'une ellipse
STRAIGHT_TOLERANCE_MM = 0.3  # écart à la corde d'une portion « droite »
CURVED_SAGITTA_MM = 0.7  # flèche de l'ellipse sur la même corde : elle se courbe


@dataclass
class Ellipse:
    center: np.ndarray
    major: float  # grand diamètre (mm)
    minor: float  # petit diamètre (mm)
    major_axis: np.ndarray  # direction du grand axe (vecteur unitaire)
    points: np.ndarray  # points du dessin sur l'ellipse (à moins de 1,2 mm)
    coverage: float  # part du contour longée par le tracé

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

    def tangent(self, points: np.ndarray) -> np.ndarray:
        """Direction (unitaire) du contour de l'ellipse à hauteur de chaque point."""
        t = self.angles(points)
        d = (np.outer(-np.sin(t) * self.major / 2, self.major_axis)
             + np.outer(np.cos(t) * self.minor / 2, self.minor_axis))
        return d / np.maximum(np.linalg.norm(d, axis=1, keepdims=True), 1e-9)

    def traced(self, points: np.ndarray, directions: np.ndarray) -> np.ndarray:
        """Points tout près de l'ellipse dont le tracé la longe (direction ``directions``)."""
        near = self.distance(points) <= TOLERANCE_MM
        along = np.abs((self.tangent(points) * directions).sum(axis=1))
        return near & (along >= np.cos(np.radians(ALIGNED_DEG)))

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


def fit(points: np.ndarray) -> Ellipse | None:
    """Ellipse ajustée sur des points, si elle n'est ni trop petite ni trop allongée."""
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


def coverage(ellipse: Ellipse, points: np.ndarray) -> float:
    """Part du contour (72 secteurs) où passent des points."""
    if not len(points):
        return 0.0
    bins = np.floor((ellipse.angles(points) + np.pi) / (2 * np.pi) * 72).astype(int) % 72
    return len(np.unique(bins)) / 72


def tangents(drawing: Drawing) -> np.ndarray:
    """Direction locale du tracé (vecteur unitaire, sur ~2 mm) en chaque point
    de ``drawing.points``."""
    found = []
    for stroke in drawing.strokes:
        pts = stroke.points
        k = min(3, len(pts) - 1)
        if k == 0:
            found.append(np.zeros_like(pts))
            continue
        ahead = np.vstack([pts[k:], np.repeat(pts[-1:], k, axis=0)])
        behind = np.vstack([np.repeat(pts[:1], k, axis=0), pts[:-k]])
        d = ahead - behind
        found.append(d / np.maximum(np.linalg.norm(d, axis=1, keepdims=True), 1e-9))
    return np.vstack(found) if found else np.zeros((0, 2))


def find_ellipses(drawing: Drawing, count: int, max_size: float | None = None) -> list[Ellipse]:
    """Jusqu'à ``count`` ellipses, de la mieux tracée à la moins bien tracée."""
    points = drawing.points
    if len(points) < 10:
        return []
    directions = tangents(drawing)
    max_size = max_size or 1.5 * drawing.extent
    candidates = _candidates(drawing, points, directions, max_size)
    free = np.ones(len(points), bool)
    found = []
    for _ in range(count):
        ranked = sorted(candidates, key=lambda c: -_score(c[0], points[c[1] & free]))
        # Les meilleures sont affinées : un tracé à main levée s'écarte de toute
        # ellipse, la part suivie change beaucoup pour un petit déplacement.
        polished = [_polish(e, points, directions, free) for e, _ in ranked[:POLISHED]]
        if not polished:
            break
        chosen = max(polished, key=lambda e: _score(e, e.points))
        if chosen.coverage < MIN_COVERAGE:
            break
        # Seuls les points qui la longent sont retirés pour chercher les
        # suivantes ; pour les mesures (intervalles, jonctions), tous les points
        # proches comptent, même là où un autre trait la croise.
        free &= ~(chosen.traced(points, directions) & free)
        chosen.points = points[chosen.distance(points) <= TOLERANCE_MM]
        found.append(chosen)
    return found


def _score(e: Ellipse, traced: np.ndarray) -> float:
    """Une ellipse bien suivie sur tout son contour d'abord, puis la plus
    grande. Chaque portion du contour compte d'autant plus que le tracé y passe
    près : une ellipse coincée entre deux traits voisins (deux ellipses
    concentriques) les longe tous deux de loin et compte peu."""
    if not len(traced):
        return 0.0
    bins = np.floor((e.angles(traced) + np.pi) / (2 * np.pi) * 72).astype(int) % 72
    closest = np.full(72, np.inf)
    np.minimum.at(closest, bins, e.distance(traced))
    near = np.clip(1 - closest / TOLERANCE_MM, 0, 1)
    return float(near.mean()) ** 2 * e.perimeter


def _polish(e: Ellipse, points: np.ndarray, directions: np.ndarray,
            free: np.ndarray) -> Ellipse:
    """Petits déplacements (centre, axes, orientation) tant que la part du
    contour suivie par le tracé augmente."""

    def placed(center, major, minor, angle) -> Ellipse:
        axis = np.array([np.cos(angle), np.sin(angle)])
        candidate = Ellipse(center, major, minor, axis, points[:0], 0.0)
        kept = points[candidate.traced(points, directions) & free]
        candidate.points, candidate.coverage = kept, coverage(candidate, kept)
        return candidate

    angle = float(np.arctan2(e.major_axis[1], e.major_axis[0]))
    state = [e.center[0], e.center[1], e.major, e.minor, angle]
    best = placed(np.array(state[:2]), *state[2:])
    for step in POLISH_STEPS:
        moves = [(0, step[0]), (1, step[0]), (2, step[1]), (3, step[1]), (4, np.radians(step[2]))]
        improved = True
        while improved:
            improved = False
            for k, delta in moves:
                for sign in (-1, 1):
                    trial = list(state)
                    trial[k] += sign * delta
                    if trial[3] < MIN_AXIS_MM or trial[3] > trial[2]:
                        continue
                    candidate = placed(np.array(trial[:2]), *trial[2:])
                    if _score(candidate, candidate.points) > _score(best, best.points) + 1e-9:
                        state, best, improved = trial, candidate, True
    return best


def _candidates(drawing: Drawing, points: np.ndarray, directions: np.ndarray,
                max_size: float) -> list[tuple[Ellipse, np.ndarray]]:
    """Ellipses ajustées sur des portions de chaque trait, puis réajustées sur
    les points qui les longent ; celles qui reviennent au même sont fusionnées."""
    tried: set[tuple[int, ...]] = set()  # ajustements sur une portion de trait
    kept: set[tuple[int, ...]] = set()  # ellipses réajustées retenues
    found = []
    start = 0
    for stroke in drawing.strokes:
        index = np.arange(start, start + len(stroke.points))
        start += len(stroke.points)
        if len(index) < 10:
            continue
        step = max(1, int(round(WINDOW_STEP_MM / STEP_MM)))
        for length in WINDOW_LENGTHS_MM:
            span = int(round(length / STEP_MM))
            for first in range(0, max(1, len(index) - span + 1), step):
                candidate = fit(points[index[first:first + span]])
                if candidate is None or candidate.major > max_size:
                    continue
                key = _key(candidate)
                if key in tried:
                    continue
                tried.add(key)
                settled = _settle(candidate, points, directions, max_size)
                if settled is not None and _key(settled[0]) not in kept:
                    kept.add(_key(settled[0]))
                    found.append(settled)
    return found


def _key(e: Ellipse) -> tuple[int, ...]:
    """Ellipses presque identiques (au mm et à 10° près) : même clé."""
    angle = np.degrees(np.arctan2(e.major_axis[1], e.major_axis[0])) % 180
    return (int(round(e.center[0])), int(round(e.center[1])), int(round(e.major)),
            int(round(e.minor)), int(round(angle / 10)) % 18)


def _settle(e: Ellipse, points: np.ndarray, directions: np.ndarray,
            max_size: float) -> tuple[Ellipse, np.ndarray] | None:
    """Réajuste l'ellipse sur les points qui la longent, jusqu'à ce qu'elle bouge peu."""
    for _ in range(3):
        traced = e.traced(points, directions)
        refit = fit(points[traced])
        if refit is None or refit.major > max_size:
            break
        e = refit
    traced = e.traced(points, directions)
    if traced.sum() < 6:
        return None
    return e, traced


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
    points, directions = drawing.points, tangents(drawing)
    if exclude is not None and len(exclude):
        far = np.sqrt(((points[:, None, :] - exclude[None, :, :]) ** 2).sum(-1)).min(1)
        points, directions = points[far > TOLERANCE_MM / 2], directions[far > TOLERANCE_MM / 2]
    best = None
    for scale in np.concatenate([scales, 1 / scales]):
        candidate = Ellipse(ellipse.center, ellipse.major * scale, ellipse.minor * scale,
                            ellipse.major_axis, points[:0], 0.0)
        traced = points[candidate.traced(points, directions)]
        share = coverage(candidate, traced)
        if best is None or share > best.coverage:
            candidate.points, candidate.coverage = traced, share
            best = candidate
    if best is None or best.coverage < MIN_COVERAGE:
        return None
    refit = fit(best.points)
    if refit is not None and np.linalg.norm(refit.center - ellipse.center) < 0.2 * ellipse.minor:
        traced = points[refit.traced(points, directions)]
        refit.points, refit.coverage = traced, coverage(refit, traced)
        if refit.coverage >= best.coverage:
            best = refit
    best.points = points[best.distance(points) <= TOLERANCE_MM]  # pour les mesures
    return best
