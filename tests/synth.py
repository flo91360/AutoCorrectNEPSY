"""Dessins et pages synthétiques pour les tests (aucune donnée réelle d'enfant)."""

from __future__ import annotations

import cv2
import numpy as np

DPI = 200
PX_PER_MM = DPI / 25.4
BLUE_PEN = (200, 80, 30)  # BGR
DARK_BLUE_PEN = (72, 60, 54)  # encre épaisse : bleu presque noir, peu saturé
PRINT_BLACK = (30, 30, 30)
PENCIL = (120, 120, 120)
BACKGROUND = (235, 235, 235)


def canvas(width_mm: float = 64, height_mm: float = 88, ppm: float = PX_PER_MM) -> np.ndarray:
    return np.full((int(height_mm * ppm), int(width_mm * ppm), 3), BACKGROUND, np.uint8)


def _wobble(points: np.ndarray, amplitude: float, seed: int) -> np.ndarray:
    """Ajoute un léger tremblement de main (en mm), nul aux extrémités."""
    if amplitude <= 0:
        return points
    rng = np.random.default_rng(seed)
    noise = np.cumsum(rng.normal(0, amplitude / 4, points.shape), axis=0)
    noise -= np.linspace(noise[0], noise[-1], len(points))
    return points + np.clip(noise, -amplitude, amplitude)


def polyline(image: np.ndarray, points_mm, color=BLUE_PEN, width_mm: float = 0.45,
             closed: bool = False, wobble: float = 0.0, seed: int = 0,
             ppm: float = PX_PER_MM, offset=(0.0, 0.0)) -> np.ndarray:
    points = np.asarray(points_mm, float) + np.asarray(offset, float)
    ends = np.vstack([points[1:], points[:1]]) if closed else points[1:]
    dense = [points[0]]
    for a, b in zip(points, ends):
        n = max(2, int(np.linalg.norm(b - a) / 0.3))
        dense.extend(np.linspace(a, b, n)[1:])
    dense = _wobble(np.array(dense), wobble, seed)
    pts = np.round(dense * ppm).astype(np.int32)
    cv2.polylines(image, [pts], False, color, max(1, int(round(width_mm * ppm))), cv2.LINE_AA)
    return image


def dot(image: np.ndarray, center_mm, diameter_mm: float, color=BLUE_PEN,
        ppm: float = PX_PER_MM, offset=(0.0, 0.0)) -> np.ndarray:
    """Cercle plein (rond colorié au stylo)."""
    x, y = (np.asarray(center_mm, float) + np.asarray(offset, float)) * ppm
    cv2.circle(image, (int(round(x)), int(round(y))), max(1, int(round(diameter_mm * ppm / 2))),
               color, -1, cv2.LINE_AA)
    return image


def dot_row(start, step, count: int = 10):
    """Centres de ``count`` marques espacées de ``step`` (mm) à partir de ``start``."""
    return [np.asarray(start, float) + i * np.asarray(step, float) for i in range(count)]


def s_curve(center, vertical: bool = False, half: float = 18.0, bulge: float = 7.0):
    """Ligne en « S » du modèle de l'item 12 : creux puis crête, extrémités
    qui recoupent un peu l'axe. Verticale : même ligne tournée d'un quart de tour."""
    t = np.linspace(-half, half, 200)
    across = -bulge * np.sin(np.pi * t / 16)
    x, y = (-across, t) if vertical else (t, across)
    return np.column_stack([center[0] + x, center[1] + y])


def cylinder(center, half_length: float = 17.4, radius: float = 9.3, depth: float = 6.2,
             back_depth: float | None = None):
    """Cylindre couché de l'item 14, incliné à 45° vers le bas à droite :
    ellipse à l'avant (en bas à droite), arrière incurvé vers l'extérieur.
    Renvoie (points, fermé, graine) pour chaque trait."""
    c = np.asarray(center, float)
    u = np.array([1.0, 1.0]) / np.sqrt(2)  # axe, vers l'avant
    n = np.array([1.0, -1.0]) / np.sqrt(2)  # en travers
    back, front = c - half_length * u, c + half_length * u
    back_depth = depth if back_depth is None else back_depth
    theta = np.linspace(0, 2 * np.pi, 240)
    ellipse = front + np.outer(radius * np.cos(theta), n) + np.outer(depth * np.sin(theta), u)
    half = np.linspace(0, np.pi, 120)
    arc = back + np.outer(radius * np.cos(half), n) - np.outer(back_depth * np.sin(half), u)
    return [(ellipse, True, 0), (arc, False, 1),
            ([back + radius * n, front + radius * n], False, 2),
            ([back - radius * n, front - radius * n], False, 3)]


def cross_points(center, half_width: float = 6.0, arm: float = 11.0, arms=None):
    """Contour de la croix de l'item 15 (12 sommets, en partant du haut à
    gauche). ``arms`` : longueurs des branches haut, droite, bas, gauche."""
    x, y = center
    w = half_width
    top, right, bottom, left = arms or (arm,) * 4
    return [(x - w, y - w - top), (x + w, y - w - top), (x + w, y - w), (x + w + right, y - w),
            (x + w + right, y + w), (x + w, y + w), (x + w, y + w + bottom),
            (x - w, y + w + bottom), (x - w, y + w), (x - w - left, y + w),
            (x - w - left, y - w), (x - w, y - w)]


def circle_points(center, radius: float, start_deg: float = 0, sweep_deg: float = 360,
                  ry: float | None = None) -> np.ndarray:
    angles = np.radians(np.linspace(start_deg, start_deg + sweep_deg, 240))
    ry = radius if ry is None else ry
    return np.column_stack([center[0] + radius * np.cos(angles), center[1] + ry * np.sin(angles)])


def draw_model(item: int, image: np.ndarray, color=BLUE_PEN, wobble: float = 0.0,
               ppm: float = PX_PER_MM, offset=(0.0, 0.0)) -> np.ndarray:
    """Copie fidèle du modèle de l'item, centrée dans une zone de 64 x 88 mm."""
    def draw(points, **kwargs):
        kwargs.setdefault("wobble", wobble)
        polyline(image, points, color, ppm=ppm, offset=offset, **kwargs)

    if item == 1:
        draw([(32, 24), (32, 64)])
    elif item == 2:
        draw([(10, 44), (55, 44)])
    elif item == 3:
        draw(circle_points((32, 44), 20), closed=True)
    elif item == 4:
        draw([(12, 24), (52, 24), (52, 64), (12, 64)], closed=True)
    elif item == 5:
        draw([(20, 14), (20, 74)])
        draw([(20, 44), (50, 44)], seed=1)
    elif item == 6:
        draw([(9.5, 31), (32, 70), (54.5, 31)])
    elif item == 7:
        draw([(22, 14), (22, 74)])
        draw([(42, 14), (42, 74)], seed=1)
        draw([(8, 44), (56, 44)], seed=2)
    elif item == 8:
        for i, y in enumerate((24, 44, 64)):
            draw(circle_points((32, y), 13), closed=True, seed=i)
    elif item == 9:
        rng = np.random.default_rng(9)
        for center in dot_row((18, 58), (3, -3)):
            jitter = rng.uniform(-1, 1, 2) * wobble * 0.3
            dot(image, center + jitter, 1.9, color, ppm, offset)
    elif item == 10:
        draw([(20, 42), (32, 20), (44, 42)])
        draw([(14, 42), (50, 42), (44, 51), (20, 51)], closed=True, seed=1)
    elif item == 11:
        draw([(4, 24), (60, 24), (60, 64), (4, 64)], closed=True)
        draw([(4, 43), (24, 43), (24, 24)], seed=1)
    elif item == 12:
        draw(s_curve((32, 44)))
        draw(s_curve((32, 44), vertical=True), seed=1)
    elif item == 13:
        # Barre grisée de 2 mm : le tremblement d'une copie fidèle reste plus faible.
        draw([(7, 58), (57, 58)], wobble=wobble * 0.6)
        for i, angle in enumerate(np.radians(np.arange(22.5, 180, 22.5)), start=1):
            draw([(32, 58), (32 + 25 * np.cos(angle), 58 - 25 * np.sin(angle))], seed=i,
                 wobble=wobble * 0.6)
    elif item == 14:
        for points, closed, seed in cylinder((32, 44)):
            # Barre grisée de 2 mm : le tremblement d'une copie fidèle reste plus faible.
            draw(points, closed=closed, seed=seed, wobble=wobble * 0.6)
    elif item == 15:
        # Côtés de 11 et 12 mm comparés à 1,2:1 près : tremblement plus faible.
        draw(cross_points((32, 44)), closed=True, wobble=wobble * 0.6)
    else:
        raise ValueError(item)
    return image


# -- page complète du cahier ----------------------------------------------------
PAGE_W_MM, PAGE_H_MM = 297, 210
SEPARATOR_Y_MM = 105
LINE_GRAY = (180, 180, 180)
COLUMNS_MM = {
    4: (20, 84.25, 148.5, 212.75, 277),
    3: (20, 105.7, 191.3, 277),
    "page1": (20, 84, 148, 212),  # l'en-tête occupe la droite de la page 1
}


def page(items_by_column: dict[int, int], layout=4, ppm: float = 100 / 25.4) -> np.ndarray:
    """Page du cahier dans le sens de passation : modèles imprimés en haut,
    copies de l'enfant au stylo bleu en bas. ``layout`` vaut 4, 3 ou "page1"."""
    bounds = COLUMNS_MM[layout]
    image = np.full((int(PAGE_H_MM * ppm), int(PAGE_W_MM * ppm), 3), 245, np.uint8)

    def px(x, y):
        return int(round(x * ppm)), int(round(y * ppm))

    thickness = max(1, int(round(0.3 * ppm)))
    cv2.line(image, px(bounds[0], SEPARATOR_Y_MM), px(bounds[-1], SEPARATOR_Y_MM),
             LINE_GRAY, thickness)
    for x in bounds[1:-1]:
        cv2.line(image, px(x, 15), px(x, 195), LINE_GRAY, thickness)
    for column, item in items_by_column.items():
        x0 = bounds[column]
        draw_model(item, image, PRINT_BLACK, ppm=ppm, offset=(x0, 15))
        draw_model(item, image, BLUE_PEN, ppm=ppm, offset=(x0, SEPARATOR_Y_MM))
    return image
