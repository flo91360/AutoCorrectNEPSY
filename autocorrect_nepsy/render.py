"""Image « traits lus par l'outil » du rapport, avec les mesures dessinées
dessus (longueurs, angles, barres grisées, diamètres, chevauchements) pour que
l'ergothérapeute puisse vérifier chaque mesure.
"""

from __future__ import annotations

import unicodedata
from functools import lru_cache

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from . import geometry as geo

DISPLAY_WIDTH = 400  # largeur affichée dans le rapport (px)
RENDER_SCALE = 2  # image dessinée en double résolution pour rester nette
LABEL_SIZE = 13  # taille du texte affiché (px)

# Couleurs (RVB).
STROKE_COLORS = [(220, 40, 40), (30, 150, 30), (20, 90, 200), (230, 140, 0),
                 (170, 40, 170), (0, 150, 150), (160, 60, 90)]
LINE_COLOR = (150, 150, 150)
MARK_COLOR = (30, 41, 59)
BAND_COLOR = (148, 163, 184)
BAND_OPACITY = 0.3

COTE_OFFSET_MM = 4.0  # distance entre le trait mesuré et sa cote
TICK_MM = 1.0
ANGLE_RADIUS_MM = 6.0
FONT_FILES = ("segoeui.ttf", "arial.ttf", "DejaVuSans.ttf", "LiberationSans-Regular.ttf")


@lru_cache(maxsize=4)
def _font(size: int) -> tuple[ImageFont.ImageFont, bool]:
    """Police du système (accents, « Ø ») ou, à défaut, police intégrée de
    Pillow ; le booléen indique s'il faut retirer les accents."""
    for name in FONT_FILES:
        try:
            return ImageFont.truetype(name, size), False
        except OSError:
            continue
    return ImageFont.load_default(size=size), True


def _plain(text: str) -> str:
    text = text.replace("Ø", "diam.")
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def _bgr(rgb: tuple[int, int, int]) -> tuple[int, int, int]:
    return rgb[2], rgb[1], rgb[0]


class _Canvas:
    """Image en pixels où l'on dessine avec des coordonnées en mm."""

    def __init__(self, width_px: int, height_px: int, px_per_mm: float, center_mm: np.ndarray):
        self.image = np.full((height_px, width_px, 3), 255, np.uint8)
        self.k = px_per_mm
        self.center = center_mm
        self.labels: list[tuple[str, np.ndarray, np.ndarray]] = []  # texte, ancre, direction

    def px(self, p) -> tuple[int, int]:
        return int(round(p[0] * self.k)), int(round(p[1] * self.k))

    def line(self, a, b, color, width=1) -> None:
        cv2.line(self.image, self.px(a), self.px(b), _bgr(color), width, cv2.LINE_AA)

    def away(self, a, b) -> np.ndarray:
        """Normale au segment ab, tournée vers l'extérieur du dessin."""
        direction = geo.unit(np.asarray(b) - np.asarray(a))
        normal = np.array([-direction[1], direction[0]])
        if (np.asarray(a) + np.asarray(b)) / 2 @ normal < self.center @ normal:
            normal = -normal
        return normal

    def label(self, text: str, anchor, direction=(0.0, -1.0)) -> None:
        self.labels.append((text, np.asarray(anchor, float), geo.unit(np.asarray(direction, float))))


def measured_image(zone_shape: tuple[int, int], px_per_mm: float, strokes, lines,
                   marks, stroke_width: float) -> np.ndarray:
    """Traits reconstruits et repères de mesure, sur fond blanc (image BGR)."""
    height, width = zone_shape[:2]
    scale = RENDER_SCALE * DISPLAY_WIDTH / width
    k = px_per_mm * scale
    points = np.vstack([s.points for s in strokes]) if strokes else np.zeros((1, 2))
    canvas = _Canvas(int(width * scale), int(height * scale), k, points.mean(axis=0))

    bands = [m for m in marks if m.kind == "bande"]
    if bands:
        overlay = canvas.image.copy()
        for mark in bands:
            poly = np.array([canvas.px(p) for p in mark.points], np.int32)
            cv2.fillPoly(overlay, [poly], _bgr(BAND_COLOR), cv2.LINE_AA)
        canvas.image = cv2.addWeighted(overlay, BAND_OPACITY, canvas.image, 1 - BAND_OPACITY, 0)

    thickness = max(2, int(round(max(stroke_width, 0.3) * k)))
    for i, stroke in enumerate(strokes):
        pts = np.array([canvas.px(p) for p in stroke.points], np.int32)
        cv2.polylines(canvas.image, [pts], stroke.closed, _bgr(STROKE_COLORS[i % len(STROKE_COLORS)]),
                      thickness, cv2.LINE_AA)
    for line in lines:
        canvas.line(*line.ends, LINE_COLOR, 1)

    for mark in marks:
        _DRAW[mark.kind](canvas, mark)
    image = _draw_labels(canvas)
    _scale_bar(image, k)
    return image


def _draw_cote(canvas: _Canvas, mark) -> None:
    a, b = mark.points
    side = mark.extra.get("side")
    normal = geo.unit(side) if side is not None else canvas.away(a, b)
    a2, b2 = a + normal * COTE_OFFSET_MM, b + normal * COTE_OFFSET_MM
    for p, q in ((a, a2), (b, b2)):
        canvas.line(p + normal * 0.8, q + normal * 0.8, MARK_COLOR, 1)
    canvas.line(a2, b2, MARK_COLOR, 2)
    along = geo.unit(b - a)
    for p in (a2, b2):
        canvas.line(p - (along - normal) * TICK_MM * 0.6, p + (along - normal) * TICK_MM * 0.6,
                    MARK_COLOR, 2)
    canvas.label(mark.label, (a2 + b2) / 2, normal)


def _draw_segment(canvas: _Canvas, mark) -> None:
    a, b = mark.points
    canvas.line(a, b, MARK_COLOR, 2)
    along = geo.unit(b - a)
    normal = np.array([-along[1], along[0]])
    for p in (a, b):
        canvas.line(p - normal * TICK_MM, p + normal * TICK_MM, MARK_COLOR, 2)
    # Étiquette au bout le plus extérieur, dans le prolongement du segment : à
    # l'intérieur d'un cercle, elle se confondrait avec d'autres mesures.
    far, near = sorted((a, b), key=lambda p: -np.linalg.norm(p - canvas.center))
    canvas.label(mark.label, far, far - near)


def _draw_angle(canvas: _Canvas, mark) -> None:
    vertex, p1, p2 = mark.points
    u, v = geo.unit(p1 - vertex), geo.unit(p2 - vertex)
    arms = min(np.linalg.norm(p1 - vertex), np.linalg.norm(p2 - vertex))
    radius = max(2.5, min(ANGLE_RADIUS_MM, 0.45 * arms))
    a1 = np.degrees(np.arctan2(u[1], u[0]))
    a2 = np.degrees(np.arctan2(v[1], v[0]))
    sweep = (a2 - a1 + 360) % 360
    if sweep > 180:
        a1, sweep = a2, 360 - sweep
    r = int(round(radius * canvas.k))
    cv2.ellipse(canvas.image, canvas.px(vertex), (r, r), 0, a1, a1 + sweep, _bgr(MARK_COLOR), 2,
                cv2.LINE_AA)
    middle = np.radians(a1 + sweep / 2)
    bisector = np.array([np.cos(middle), np.sin(middle)])
    canvas.label(mark.label, vertex + bisector * radius, bisector)


def _draw_point(canvas: _Canvas, mark) -> None:
    [p] = mark.points
    cv2.circle(canvas.image, canvas.px(p), int(round(0.9 * canvas.k)), _bgr(MARK_COLOR), 2,
               cv2.LINE_AA)
    canvas.label(mark.label, p, (1.0, 1.0))


def _draw_circle(canvas: _Canvas, mark) -> None:
    [center] = mark.points
    cv2.circle(canvas.image, canvas.px(center), max(2, int(round(mark.radius * canvas.k))),
               _bgr(MARK_COLOR), 2, cv2.LINE_AA)
    direction = np.array([1.0, 0.0]) if center[0] >= canvas.center[0] else np.array([-1.0, 0.0])
    canvas.label(mark.label, center + direction * mark.radius, direction)


def _draw_band(canvas: _Canvas, mark) -> None:
    """Étiquette au milieu de la bande, côté intérieur du dessin, ou au bout le
    plus éloigné du centre, pour qu'on voie à quel trait elle se rapporte."""
    corners = mark.points
    if mark.extra.get("at") == "bout":
        ends = [(corners[0] + corners[3]) / 2, (corners[1] + corners[2]) / 2]
        far, near = sorted(ends, key=lambda p: -np.linalg.norm(p - canvas.center))
        canvas.label(mark.label, far, far - near)
        return
    middle = np.mean(corners, axis=0)
    inward = canvas.center - middle
    if np.linalg.norm(inward) < 2.0:
        inward = corners[3] - corners[0]
    canvas.label(mark.label, middle, inward)


_DRAW = {"cote": _draw_cote, "segment": _draw_segment, "angle": _draw_angle,
         "point": _draw_point, "cercle": _draw_circle, "bande": _draw_band}


def _draw_labels(canvas: _Canvas) -> np.ndarray:
    """Pose les étiquettes là où elles cachent le moins de traits et d'autres
    étiquettes, en partant de la direction proposée par chaque repère."""
    busy = (canvas.image.min(axis=2) < 200).astype(np.uint8)
    integral = cv2.integral(busy, sdepth=cv2.CV_32S)
    pil = Image.fromarray(cv2.cvtColor(canvas.image, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(pil)
    font, plain = _font(LABEL_SIZE * RENDER_SCALE)
    pad = 2 * RENDER_SCALE
    gap = 1.0 * canvas.k
    w_img, h_img = pil.size
    placed: list[tuple[int, int, int, int]] = []
    for text, anchor, direction in canvas.labels:
        text = _plain(text) if plain else text
        left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
        w, h = right - left + 2 * pad, bottom - top + 2 * pad
        ax, ay = canvas.px(anchor)
        best = None
        for rank, d in enumerate(_directions(direction)):
            reach = gap + abs(d[0]) * w / 2 + abs(d[1]) * h / 2
            cx, cy = ax + d[0] * reach, ay + d[1] * reach
            x0 = int(min(max(cx - w / 2, 0), w_img - w))
            y0 = int(min(max(cy - h / 2, 0), h_img - h))
            box = (x0, y0, x0 + w, y0 + h)
            ink = (integral[box[3], box[2]] - integral[box[1], box[2]]
                   - integral[box[3], box[0]] + integral[box[1], box[0]])
            cost = ink + 5000 * sum(_overlap(box, other) for other in placed) + 40 * rank
            if best is None or cost < best[0]:
                best = (cost, box)
        box = best[1]
        placed.append(box)
        draw.rounded_rectangle(box, radius=3 * RENDER_SCALE, fill=(255, 255, 255),
                               outline=(203, 213, 225), width=1)
        draw.text((box[0] + pad - left, box[1] + pad - top), text, font=font, fill=MARK_COLOR)
    return cv2.cvtColor(np.asarray(pil), cv2.COLOR_RGB2BGR)


def _directions(preferred) -> list[np.ndarray]:
    """La direction proposée, puis les directions voisines, puis les autres."""
    base = np.arctan2(preferred[1], preferred[0])
    turns = [0, 45, -45, 90, -90, 135, -135, 180]
    return [np.array([np.cos(base + np.radians(t)), np.sin(base + np.radians(t))]) for t in turns]


def _overlap(a, b) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def _scale_bar(image: np.ndarray, k: float) -> None:
    h = image.shape[0]
    x0, y0 = int(5 * k), h - int(5 * k)
    cv2.line(image, (x0, y0), (x0 + int(10 * k), y0), (0, 0, 0), 2)
    cv2.putText(image, "1 cm", (x0, y0 - int(1.5 * k)), cv2.FONT_HERSHEY_SIMPLEX,
                0.04 * k, (0, 0, 0), 1, cv2.LINE_AA)
