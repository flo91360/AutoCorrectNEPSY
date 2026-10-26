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


def nested_triangles(apex, width: float = 35.5, height: float = 35.5, small_shift=(0.0, 0.0)):
    """Item 16 : grand triangle, triangle moyen inversé (milieux des côtés),
    petit triangle (milieux des côtés du moyen, décalé de ``small_shift``)
    et lignes des coins du grand aux coins du petit."""
    a = np.asarray(apex, float)
    bl, br = a + (-width / 2, height), a + (width / 2, height)
    m1, m2, m3 = (a + bl) / 2, (a + br) / 2, (bl + br) / 2
    shift = np.asarray(small_shift, float)
    s1, s2, s3 = (m1 + m2) / 2 + shift, (m1 + m3) / 2 + shift, (m2 + m3) / 2 + shift
    return [[a, bl, br], [m1, m2, m3], [s1, s2, s3], [a, s1], [bl, s2], [br, s3]]


def v_shape(bottom_center, top: float = 18.0, base: float = 18.0, height: float = 31.0,
            width: float = 55.4, tilt: float = 0.0):
    """Les deux parallélogrammes de l'item 17, qui se croisent au-dessus de la
    base du V (centre de la base ``bottom_center``). ``tilt`` : pente (mm)
    des côtés horizontaux du haut, vers le bas à l'extérieur."""
    x, y = bottom_center
    b0, b1 = x - base / 2, x + base / 2
    left = [(x - width / 2, y - height + tilt), (x - width / 2 + top, y - height), (b1, y), (b0, y)]
    right = [(x + width / 2 - top, y - height), (x + width / 2, y - height + tilt), (b1, y), (b0, y)]
    return left, right


def stairs_points(top_left, step: float = 12.3, steps: int = 4, heights=None):
    """Contour de l'escalier de l'item 18 (``heights`` : hauteur de chaque
    marche, de haut en bas)."""
    x, y = top_left
    heights = heights or [step] * steps
    points = [(x, y)]
    for i, h in enumerate(heights):
        points += [(x + (i + 1) * step, y), (x + (i + 1) * step, y + h)]
        y += h
    return points + [(x, y)]


def bucket(top_center, a: float = 28.0, b: float = 15.6, inner: float = 0.8, drop: float = 24.0,
           base_scale: float = 1.0):
    """Seau de l'item 19 : deux ellipses concentriques en haut, verticales, et
    ellipse de base visible à l'avant et dans l'ouverture. Renvoie (points,
    fermé) pour chaque trait."""
    x, y = top_center
    t = np.linspace(0, 2 * np.pi, 360)
    outer = np.column_stack([x + a * np.cos(t), y + b * np.sin(t)])
    inner_pts = np.column_stack([x + inner * a * np.cos(t), y + inner * b * np.sin(t)])
    ba, bb, by = a * base_scale, b * base_scale, y + drop
    front = np.column_stack([x + ba * np.cos(t[:181]), by + bb * np.sin(t[:181])])
    back = np.column_stack([x + ba * np.cos(t[180:]), by + bb * np.sin(t[180:])])
    seen = (((back[:, 0] - x) / (inner * a)) ** 2 + ((back[:, 1] - y) / (inner * b)) ** 2) < 1
    strokes = [(outer, True), (inner_pts, True), (front, False),
               ([(x - a, y), (x - ba, by)], False), ([(x + a, y), (x + ba, by)], False)]
    if seen.any():
        strokes.append((back[seen], False))
    return strokes


def flower(center, petals: int = 6, length: float = 30.0, width: float = 8.0, bend: float = 1.5,
           start_deg: float = 90.0, lengths=None, starts=None, blunt: bool = False):
    """Fleur de l'item 20 : pétales pointus aux bords en « S », tournant tous
    dans le même sens. ``starts`` : distance au centre où part chaque pétale ;
    ``blunt`` : bouts arrondis. Renvoie le contour de chaque pétale."""
    c = np.asarray(center, float)
    found = []
    for k in range(petals):
        size = lengths[k] if lengths else length
        angle = np.radians(start_deg + k * 360.0 / petals)
        along = np.array([np.cos(angle), -np.sin(angle)])
        across = np.array([-along[1], along[0]])
        base = c + along * (starts[k] if starts else 0.0)
        u = np.linspace(0, 1, 80)
        if blunt:
            r = width / 2
            s = u * size
            half = np.where(s > size - r, np.sqrt(np.clip(r ** 2 - (s - size + r) ** 2, 0, None)),
                            r * np.sin(np.pi * np.minimum(u, 0.5)) ** 0.8)
        else:
            half = width / 2 * np.sin(np.pi * u) ** 0.8
        shift = bend * np.sin(2 * np.pi * u)
        left = base + np.outer(u * size, along) + np.outer(half + shift, across)
        right = base + np.outer(u * size, along) + np.outer(-half + shift, across)
        found.append(np.vstack([left, right[::-1][1:-1]]))
    return found


def wheels(left_center=(27, 52), left: float = 25.0, right: float = 20.0, offset=(15, -15),
           chords=(6, 6), tilt: float = 0.0, axle: bool = True):
    """Deux roues de l'item 21 (rayons ``left`` et ``right``), ``chords``
    diamètres régulièrement espacés dans chacune (le premier horizontal, tourné
    de ``tilt`` degrés) et l'essieu entre les centres. Renvoie (points, fermé)
    pour chaque trait."""
    a = np.asarray(left_center, float)
    b = a + np.asarray(offset, float)
    strokes = [(circle_points(a, left), True), (circle_points(b, right), True)]
    for center, radius, count in ((a, left, chords[0]), (b, right, chords[1])):
        for k in range(count):
            angle = np.radians(tilt + k * 180.0 / count)
            u = np.array([np.cos(angle), -np.sin(angle)]) * radius
            strokes.append(([center - u, center + u], False))
    if axle:
        strokes.append(([a, b], False))
    return strokes


def circle_points(center, radius: float, start_deg: float = 0, sweep_deg: float = 360,
                  ry: float | None = None) -> np.ndarray:
    angles = np.radians(np.linspace(start_deg, start_deg + sweep_deg, 240))
    ry = radius if ry is None else ry
    return np.column_stack([center[0] + radius * np.cos(angles), center[1] + ry * np.sin(angles)])


def rounded_rectangle(x0: float, y0: float, x1: float, y1: float, radius: float) -> np.ndarray:
    """Contour d'un rectangle aux coins arrondis (quart de cercle de ``radius`` mm)."""
    arcs = []
    for (cx, cy), start in zip([(x1 - radius, y0 + radius), (x1 - radius, y1 - radius),
                                (x0 + radius, y1 - radius), (x0 + radius, y0 + radius)],
                               (-90, 0, 90, 180)):
        angles = np.radians(np.linspace(start, start + 90, 20))
        arcs.append(np.column_stack([cx + radius * np.cos(angles), cy + radius * np.sin(angles)]))
    return np.vstack(arcs)


def zigzag(x: float, top: float, bottom: float, amplitude: float, step: float = 5.0) -> np.ndarray:
    """Trait vertical tracé en zigzag de ± ``amplitude`` mm."""
    ys = np.arange(top, bottom + 1e-9, step)
    return np.column_stack([x + amplitude * (-1) ** np.arange(1, len(ys) + 1), ys])


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
    elif item == 16:
        # Figure dense (côtés de 10 à 18 mm) : tremblement d'une copie fidèle plus faible.
        for i, points in enumerate(nested_triangles((32, 26))):
            draw(points, closed=len(points) == 3, seed=i, wobble=wobble * 0.6)
    elif item == 17:
        left, right = v_shape((32, 57))
        draw(left, closed=True)
        draw(right, closed=True, seed=1)
    elif item == 18:
        draw(stairs_points((7.5, 20)), closed=True)
    elif item == 19:
        for i, (points, closed) in enumerate(bucket((32, 30))):
            draw(points, closed=closed, seed=i)
    elif item == 20:
        for i, petal in enumerate(flower((32, 44))):
            draw(petal, closed=True, seed=i)
    elif item == 21:
        for i, (points, closed) in enumerate(wheels()):
            draw(points, closed=closed, seed=i)
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


def page(items_by_column: dict[int, int], layout=4, ppm: float = 100 / 25.4,
         models: bool = True) -> np.ndarray:
    """Page du cahier dans le sens de passation : modèles imprimés en haut,
    copies de l'enfant au stylo bleu en bas. ``layout`` vaut 4, 3 ou "page1" ;
    ``models=False`` : modèles illisibles (absents du scan)."""
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
        if models:
            draw_model(item, image, PRINT_BLACK, ppm=ppm, offset=(x0, 15))
        draw_model(item, image, BLUE_PEN, ppm=ppm, offset=(x0, SEPARATOR_Y_MM))
    return image
