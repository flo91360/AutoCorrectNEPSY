"""Enchaînement complet : scans -> zones -> tracés -> cotation."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .criteria import SUPPORTED_ITEMS, ItemResult, score_item
from .layout import analyse_page
from .scan import load_pages
from .strokes import Drawing, extract_drawing

# Longueur attendue du trait de séparation modèles / dessins (mm), plus court en
# page 1 à cause de l'en-tête. Une valeur très différente signale une résolution
# de scan erronée (image redimensionnée).
SEPARATOR_MM = {1: 200.0}
SEPARATOR_DEFAULT_MM = 260.0
SEPARATOR_TOLERANCE = 0.08


@dataclass
class ItemReport:
    item: int
    page: int
    source: str
    result: ItemResult
    drawing: Drawing
    zone_image: np.ndarray
    px_per_mm: float


@dataclass
class Correction:
    items: list[ItemReport] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def correct(files: list[str | Path], pages: list[int] | None = None, ink: str = "bleu",
            dpi: float | None = None) -> Correction:
    """Corrige les items pris en charge présents sur les pages scannées.

    ``pages`` donne le numéro de page du cahier (1 à 6) de chaque page
    scannée, dans l'ordre ; par défaut 1, 2, 3...
    """
    scanned = [page for path in files for page in load_pages(path, dpi)]
    numbers = pages or list(range(1, len(scanned) + 1))
    if len(numbers) != len(scanned):
        raise ValueError(f"{len(scanned)} page(s) scannée(s) mais {len(numbers)} numéro(s) de page")
    correction = Correction()
    for page, number in zip(scanned, numbers):
        layout = analyse_page(page, number, ink)
        separator_mm = layout.separator.length / layout.px_per_mm
        expected = SEPARATOR_MM.get(number, SEPARATOR_DEFAULT_MM)
        if abs(separator_mm - expected) > SEPARATOR_TOLERANCE * expected:
            correction.warnings.append(
                f"{page.source} : échelle douteuse (trait de séparation de {separator_mm:.0f} mm), "
                f"vérifier la résolution du scan ({page.dpi:.0f} dpi)")
        for zone in layout.zones:
            if zone.item not in SUPPORTED_ITEMS:
                continue
            drawing = extract_drawing(layout.drawing_ink(zone.item), layout.px_per_mm)
            x0, y0, x1, y1 = zone.drawing_box
            correction.items.append(ItemReport(
                zone.item, number, page.source, score_item(zone.item, drawing), drawing,
                layout.image[y0:y1, x0:x1].copy(), layout.px_per_mm))
    correction.items.sort(key=lambda report: report.item)
    return correction
