"""Mise en page du cahier de réponses : orientation, redressement, zones.

Dans le sens de passation (paysage), chaque page du cahier présente une
rangée de modèles imprimés en haut et, sous un long trait de séparation,
la rangée où l'enfant recopie. Des traits verticaux séparent les items.

Les scans arrivent dans n'importe quel sens. On essaie les quatre quarts de
tour et on garde celui où un long trait horizontal sépare la page en deux
avec le tracé de l'enfant en dessous (ou, page vierge, les modèles au-dessus).
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from .ink import faint_mask, ink_mask, printed_mask
from .scan import ScannedPage

ITEMS_BY_PAGE = {
    1: (1, 2, 3),
    2: (4, 5, 6, 7),
    3: (8, 9, 10, 11),
    4: (12, 13, 14, 15),
    5: (16, 17, 18),
    6: (19, 20, 21),
}

# Marge (mm) retirée autour des zones pour ne pas toucher les traits imprimés.
ZONE_MARGIN_MM = 1.5


class LayoutError(ValueError):
    """La mise en page attendue n'a pas été retrouvée sur le scan."""


@dataclass
class Line:
    pos: int  # y d'un trait horizontal, x d'un trait vertical
    start: int
    end: int

    @property
    def length(self) -> int:
        return self.end - self.start


@dataclass
class ItemZone:
    item: int
    model_box: tuple[int, int, int, int]  # x0, y0, x1, y1 (px)
    drawing_box: tuple[int, int, int, int]


@dataclass
class PageLayout:
    """Page remise dans le sens de passation, avec ses zones d'items."""

    image: np.ndarray
    ink: np.ndarray
    px_per_mm: float
    quarter_turns: int
    skew_deg: float
    separator: Line
    zones: list[ItemZone]

    def zone(self, item: int) -> ItemZone:
        for zone in self.zones:
            if zone.item == item:
                return zone
        raise KeyError(f"item {item} absent de cette page")

    def drawing_ink(self, item: int) -> np.ndarray:
        x0, y0, x1, y1 = self.zone(item).drawing_box
        return self.ink[y0:y1, x0:x1]


def analyse_page(page: ScannedPage, page_number: int, ink: str = "bleu") -> PageLayout:
    """Redresse la page, l'oriente et découpe les zones de ses items."""
    if page_number not in ITEMS_BY_PAGE:
        raise LayoutError(f"numéro de page invalide : {page_number} (1 à 6)")
    image, skew = deskew(page.image)
    image, turns, separator = _orient(image, ink)
    ink_px = ink_mask(image, ink)
    zones = _item_zones(image, separator, ITEMS_BY_PAGE[page_number], page.px_per_mm)
    return PageLayout(image, ink_px, page.px_per_mm, turns, skew, separator, zones)


def deskew(image: np.ndarray) -> tuple[np.ndarray, float]:
    """Corrige la légère inclinaison du scan d'après les longs traits imprimés."""
    faint = faint_mask(image) * 255
    h, w = faint.shape
    segments = cv2.HoughLinesP(
        faint, 1, np.pi / 1800, threshold=300,
        minLineLength=int(0.3 * min(h, w)), maxLineGap=10,
    )
    if segments is None:
        return image, 0.0
    angles, weights = [], []
    for x1, y1, x2, y2 in segments.reshape(-1, 4):
        angle = np.degrees(np.arctan2(y2 - y1, x2 - x1))
        angle = (angle + 45) % 90 - 45  # ramène horizontales et verticales vers 0
        if abs(angle) < 5:
            angles.append(angle)
            weights.append(np.hypot(x2 - x1, y2 - y1))
    if not angles:
        return image, 0.0
    order = np.argsort(angles)
    cumulative = np.cumsum(np.asarray(weights)[order])
    skew = float(np.asarray(angles)[order][np.searchsorted(cumulative, cumulative[-1] / 2)])
    if abs(skew) < 0.05:
        return image, 0.0
    matrix = cv2.getRotationMatrix2D((w / 2, h / 2), skew, 1.0)
    rotated = cv2.warpAffine(image, matrix, (w, h), flags=cv2.INTER_LINEAR,
                             borderMode=cv2.BORDER_REPLICATE)
    return rotated, skew


def long_lines(mask: np.ndarray, horizontal: bool, min_fraction: float) -> list[Line]:
    """Traits rectilignes horizontaux (ou verticaux) d'au moins ``min_fraction``
    de la largeur (ou hauteur) de l'image."""
    h, w = mask.shape
    span, across = (w, h) if horizontal else (h, w)
    # On repère d'abord des morceaux de trait courts, puis on les raboute :
    # un trait gris clair est souvent interrompu ou légèrement courbé.
    bridge = np.ones((1, 15) if horizontal else (15, 1), np.uint8)
    closed = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, bridge)
    piece = max(3, int(0.05 * span))
    kernel = np.ones((1, piece) if horizontal else (piece, 1), np.uint8)
    opened = cv2.morphologyEx(closed, cv2.MORPH_OPEN, kernel)
    count, _, stats, centroids = cv2.connectedComponentsWithStats(opened)
    pieces = []
    for i in range(1, count):
        x, y, bw, bh = stats[i, :4]
        if horizontal:
            pieces.append(Line(int(round(centroids[i][1])), int(x), int(x + bw)))
        else:
            pieces.append(Line(int(round(centroids[i][0])), int(y), int(y + bh)))
    lines = []
    for group in _group_by_position(pieces, tolerance=8):
        group.sort(key=lambda p: p.start)
        current = group[0]
        for p in group[1:]:
            if p.start - current.end < 0.04 * span:
                current = Line(current.pos, current.start, max(current.end, p.end))
            else:
                lines.append(current)
                current = p
        lines.append(current)
    # Les bords noirs du scanner ne sont pas des traits du cahier.
    return sorted((line for line in lines
                   if line.length >= min_fraction * span
                   and 0.015 * across < line.pos < 0.985 * across),
                  key=lambda line: line.pos)


def _group_by_position(pieces: list[Line], tolerance: int) -> list[list[Line]]:
    groups: list[list[Line]] = []
    for p in sorted(pieces, key=lambda p: p.pos):
        if groups and p.pos - groups[-1][-1].pos <= tolerance:
            groups[-1].append(p)
        else:
            groups.append([p])
    for group in groups:
        pos = int(round(np.average([p.pos for p in group], weights=[p.length for p in group])))
        for i, p in enumerate(group):
            group[i] = Line(pos, p.start, p.end)
    return groups


def _orient(image: np.ndarray, ink: str) -> tuple[np.ndarray, int, Line]:
    best = None
    for turns in range(4):
        candidate = np.ascontiguousarray(np.rot90(image, turns))
        h, w = candidate.shape[:2]
        faint = faint_mask(candidate)
        child = ink_mask(candidate, ink)
        figures = printed_mask(candidate) & (1 - _line_mask(faint))
        for line in long_lines(faint, True, 0.5):
            if not 0.3 * h < line.pos < 0.7 * h:
                continue
            # On ne regarde que la bande couverte par le trait : l'en-tête de
            # la page 1 (nom, date, souvent écrits au stylo) est en dehors.
            span_child = child[:, line.start:line.end]
            span_figures = figures[:, line.start:line.end]
            if span_child.sum() > 200:
                score = span_child[line.pos:].sum() / span_child.sum()
            else:
                score = span_figures[:line.pos].sum() / max(1, span_figures.sum())
            if best is None or score > best[0]:
                best = (score, candidate, turns, line)
    if best is None or best[0] < 0.6:
        raise LayoutError("trait de séparation modèles / dessins introuvable")
    return best[1], best[2], best[3]


def _line_mask(mask: np.ndarray) -> np.ndarray:
    """Pixels appartenant aux longs traits imprimés (cadres, séparations)."""
    h, w = mask.shape
    lines = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((1, w // 4), np.uint8))
    lines |= cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((h // 4, 1), np.uint8))
    return cv2.dilate(lines, np.ones((7, 7), np.uint8))


def _item_zones(image: np.ndarray, separator: Line, items: tuple[int, ...],
                px_per_mm: float) -> list[ItemZone]:
    h, w = image.shape[:2]
    crossing = [line for line in long_lines(faint_mask(image), False, 0.25)
                if line.start < separator.pos < line.end
                and separator.start - 20 <= line.pos <= separator.end + 20]
    bounds = sorted({separator.start, separator.end, *(line.pos for line in crossing)})
    merged: list[int] = []
    for x in bounds:
        if not merged or x - merged[-1] >= 0.03 * w:
            merged.append(x)
    columns = [(a, b) for a, b in zip(merged, merged[1:])
               if b - a >= 0.12 * separator.length]
    if len(columns) != len(items):
        raise LayoutError(
            f"{len(columns)} zones trouvées alors que la page contient {len(items)} items")
    top = min((line.start for line in crossing), default=int(0.05 * h))
    bottom = max((line.end for line in crossing), default=int(0.95 * h))
    margin = int(round(ZONE_MARGIN_MM * px_per_mm))
    zones = []
    for item, (x0, x1) in zip(items, columns):
        zones.append(ItemZone(
            item,
            (x0 + margin, top + margin, x1 - margin, separator.pos - margin),
            (x0 + margin, separator.pos + margin, x1 - margin, bottom - margin),
        ))
    return zones
