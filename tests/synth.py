"""Dessins et pages synthétiques pour les tests (aucune donnée réelle d'enfant)."""

from __future__ import annotations

import cv2
import numpy as np

DPI = 200
PX_PER_MM = DPI / 25.4
BLUE_PEN = (200, 80, 30)  # BGR
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


def circle_points(center, radius: float, start_deg: float = 0, sweep_deg: float = 360,
                  ry: float | None = None) -> np.ndarray:
    angles = np.radians(np.linspace(start_deg, start_deg + sweep_deg, 240))
    ry = radius if ry is None else ry
    return np.column_stack([center[0] + radius * np.cos(angles), center[1] + ry * np.sin(angles)])


def draw_model(item: int, image: np.ndarray, color=BLUE_PEN, wobble: float = 0.0,
               ppm: float = PX_PER_MM, offset=(0.0, 0.0)) -> np.ndarray:
    """Copie fidèle du modèle de l'item, centrée dans une zone de 64 x 88 mm."""
    def draw(points, **kwargs):
        polyline(image, points, color, wobble=wobble, ppm=ppm, offset=offset, **kwargs)

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
