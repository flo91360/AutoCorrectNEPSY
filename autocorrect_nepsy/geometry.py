"""Outils géométriques. Toutes les coordonnées sont en mm, x vers la droite,
y vers le bas (repère de l'image), dans le sens de passation du cahier."""

from __future__ import annotations

import cv2
import numpy as np


def unit(vector: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(vector))
    return vector / norm if norm > 0 else vector


def principal_axis(points: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Centre et direction principale (unitaire) d'un nuage de points."""
    center = points.mean(axis=0)
    if len(points) < 2:
        return center, np.array([1.0, 0.0])
    _, _, vt = np.linalg.svd(points - center, full_matrices=False)
    direction = vt[0]
    # Convention : direction orientée vers la droite, ou vers le bas si verticale.
    if direction[0] < -1e-9 or (abs(direction[0]) <= 1e-9 and direction[1] < 0):
        direction = -direction
    return center, direction


def angle_to_horizontal(direction: np.ndarray) -> float:
    """Écart (0 à 90°) entre une direction et l'axe horizontal de la page."""
    return float(np.degrees(np.arctan2(abs(direction[1]), abs(direction[0]))))


def angle_to_vertical(direction: np.ndarray) -> float:
    return 90.0 - angle_to_horizontal(direction)


def angle_between(u: np.ndarray, v: np.ndarray) -> float:
    """Angle (0 à 180°) entre deux vecteurs."""
    cos = np.dot(unit(u), unit(v))
    return float(np.degrees(np.arccos(np.clip(cos, -1.0, 1.0))))


def line_intersection(p1: np.ndarray, d1: np.ndarray,
                      p2: np.ndarray, d2: np.ndarray) -> np.ndarray | None:
    """Intersection de deux droites (point + direction), None si parallèles."""
    matrix = np.array([d1, -d2]).T
    if abs(np.linalg.det(matrix)) < 1e-9:
        return None
    t, _ = np.linalg.solve(matrix, p2 - p1)
    return p1 + t * d1


def min_strip_width(points: np.ndarray) -> float:
    """Largeur de la plus étroite bande droite contenant tous les points.

    C'est l'équivalent de la « barre grisée » de la grille de correction :
    un trait est droit s'il tient entièrement dans une bande de cette largeur.
    """
    if len(points) < 3:
        return 0.0
    hull = cv2.convexHull(points.astype(np.float32)).reshape(-1, 2).astype(float)
    if len(hull) < 3:
        return 0.0
    best = np.inf
    for i in range(len(hull)):
        a, b = hull[i], hull[(i + 1) % len(hull)]
        edge = b - a
        length = np.linalg.norm(edge)
        if length == 0:
            continue
        normal = np.array([-edge[1], edge[0]]) / length
        best = min(best, float(np.max(np.abs((hull - a) @ normal))))
    return best


def max_diameter(points: np.ndarray) -> float:
    """Plus grande distance entre deux points (diamètre de Feret)."""
    if len(points) < 2:
        return 0.0
    hull = cv2.convexHull(points.astype(np.float32)).reshape(-1, 2).astype(float)
    diff = hull[:, None, :] - hull[None, :, :]
    return float(np.sqrt((diff ** 2).sum(-1)).max())


def path_length(points: np.ndarray, closed: bool = False) -> float:
    if len(points) < 2:
        return 0.0
    pts = np.vstack([points, points[:1]]) if closed else points
    return float(np.linalg.norm(np.diff(pts, axis=0), axis=1).sum())


def resample(points: np.ndarray, step: float, closed: bool = False) -> np.ndarray:
    """Rééchantillonne une polyligne à pas constant (en mm)."""
    pts = np.vstack([points, points[:1]]) if closed else points
    if len(pts) < 2:
        return points.copy()
    seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    total = cum[-1]
    if total == 0:
        return points[:1].copy()
    count = max(2, int(round(total / step)) + 1)
    targets = np.linspace(0, total, count)
    if closed:
        targets = targets[:-1]
    x = np.interp(targets, cum, pts[:, 0])
    y = np.interp(targets, cum, pts[:, 1])
    return np.column_stack([x, y])


def smooth(points: np.ndarray, window: int, closed: bool = False) -> np.ndarray:
    """Moyenne glissante pour atténuer l'escalier des pixels."""
    if window < 2 or len(points) <= window:
        return points.copy()
    kernel = np.ones(window) / window
    if closed:
        pad = np.vstack([points[-window:], points, points[:window]])
        out = np.column_stack([np.convolve(pad[:, k], kernel, mode="same") for k in range(2)])
        return out[window:-window]
    out = points.copy()
    half = window // 2
    for k in range(2):
        conv = np.convolve(points[:, k], kernel, mode="valid")
        out[half:half + len(conv), k] = conv
    return out


def rdp(points: np.ndarray, epsilon: float) -> np.ndarray:
    """Indices des sommets conservés par l'algorithme de Douglas-Peucker."""
    keep = np.zeros(len(points), dtype=bool)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        start, end = stack.pop()
        if end - start < 2:
            continue
        a, b = points[start], points[end]
        chord = b - a
        norm = np.linalg.norm(chord)
        inner = points[start + 1:end]
        if norm == 0:
            dist = np.linalg.norm(inner - a, axis=1)
        else:
            dist = np.abs(chord[0] * (inner[:, 1] - a[1]) - chord[1] * (inner[:, 0] - a[0])) / norm
        i = int(np.argmax(dist))
        if dist[i] > epsilon:
            keep[start + 1 + i] = True
            stack.append((start, start + 1 + i))
            stack.append((start + 1 + i, end))
    return np.flatnonzero(keep)


def fraction_in_cone(points: np.ndarray, apex: np.ndarray, axis: np.ndarray,
                     half_angle: float) -> float:
    """Part des points vus depuis ``apex`` à moins de ``half_angle`` degrés de
    l'axe (dans un sens ou dans l'autre)."""
    vectors = points - apex
    norms = np.linalg.norm(vectors, axis=1)
    mask = norms > 1e-6
    if not mask.any():
        return 1.0
    cos = np.abs(vectors[mask] @ unit(axis)) / norms[mask]
    return float(np.mean(cos >= np.cos(np.radians(half_angle))))


def max_cone_angle(points: np.ndarray, apex: np.ndarray, axis: np.ndarray,
                   min_distance: float = 0.0) -> float:
    """Plus grand écart (degrés) à l'axe des points vus depuis ``apex``, en
    ignorant ceux à moins de ``min_distance`` mm (direction peu fiable)."""
    vectors = points - apex
    norms = np.linalg.norm(vectors, axis=1)
    mask = norms > max(min_distance, 1e-6)
    if not mask.any():
        return 0.0
    cos = np.abs(vectors[mask] @ unit(axis)) / norms[mask]
    return float(np.degrees(np.arccos(np.clip(cos.min(), -1.0, 1.0))))


def count_direction_changes(points: np.ndarray, amplitude: float) -> int:
    """Nombre de changements de direction d'un trait ondulé.

    On suit l'écart du trait à sa corde et on compte les extremums dont la
    hauteur dépasse ``amplitude`` (mm) par rapport aux extremums voisins.
    """
    if len(points) < 3:
        return 0
    a, b = points[0], points[-1]
    chord = b - a
    norm = np.linalg.norm(chord)
    if norm == 0:
        return 0
    offset = (chord[0] * (points[:, 1] - a[1]) - chord[1] * (points[:, 0] - a[0])) / norm
    changes = 0
    direction = 0  # +1 l'écart augmente, -1 il diminue
    pivot = offset[0]  # extremum courant
    for value in offset[1:]:
        if direction == 0:
            if abs(value - pivot) >= amplitude:
                direction = 1 if value > pivot else -1
                pivot = value
        elif direction == 1:
            if value > pivot:
                pivot = value
            elif pivot - value >= amplitude:
                changes += 1
                direction, pivot = -1, value
        else:
            if value < pivot:
                pivot = value
            elif value - pivot >= amplitude:
                changes += 1
                direction, pivot = 1, value
    return changes
