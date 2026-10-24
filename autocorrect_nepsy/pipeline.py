"""Enchaînement complet : scans -> zones -> tracés -> cotation."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Callable

import numpy as np

from .criteria import SUPPORTED_ITEMS, ItemResult, score_item
from .layout import ITEMS_BY_PAGE, PreparedPage, guess_page_numbers, prepare_page
from .scan import MM_PAR_POUCE, ScannedPage, load_pages
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
    pages: list[tuple[str, int]] = field(default_factory=list)  # (scan, page du cahier)


@dataclass
class PageInput:
    """Une page scannée à corriger et son numéro de page dans le cahier."""

    scan: ScannedPage
    number: int
    prepared: PreparedPage | None = None  # déjà redressée et orientée (même encre)


def page_label(number: int) -> str:
    items = ITEMS_BY_PAGE[number]
    return f"Page {number} (items {items[0]} à {items[-1]})"


def correct_pages(inputs: list[PageInput], ink: str = "bleu",
                  progress: Callable[[int, int, str], None] | None = None) -> Correction:
    """Corrige les items pris en charge présents sur les pages fournies."""
    correction = Correction()
    for index, page in enumerate(inputs):
        if progress:
            progress(index, len(inputs), page.scan.source)
        prepared = page.prepared or prepare_page(page.scan, ink)
        # La résolution a pu être corrigée à la main depuis la préparation.
        prepared = replace(prepared, px_per_mm=page.scan.dpi / MM_PAR_POUCE)
        layout = prepared.layout(page.number)
        correction.pages.append((page.scan.source, page.number))
        separator_mm = layout.separator.length / layout.px_per_mm
        expected = SEPARATOR_MM.get(page.number, SEPARATOR_DEFAULT_MM)
        if abs(separator_mm - expected) > SEPARATOR_TOLERANCE * expected:
            correction.warnings.append(
                f"{page.scan.source} : échelle douteuse (trait de séparation de "
                f"{separator_mm:.0f} mm), vérifier la résolution du scan ({page.scan.dpi:.0f} dpi)")
        for zone in layout.zones:
            if zone.item not in SUPPORTED_ITEMS:
                continue
            drawing = extract_drawing(layout.drawing_ink(zone.item), layout.px_per_mm)
            x0, y0, x1, y1 = zone.drawing_box
            correction.items.append(ItemReport(
                zone.item, page.number, page.scan.source, score_item(zone.item, drawing), drawing,
                layout.image[y0:y1, x0:x1].copy(), layout.px_per_mm))
    if progress:
        progress(len(inputs), len(inputs), "")
    correction.items.sort(key=lambda report: report.item)
    return correction


def correct(files: list[str | Path], pages: list[int] | None = None, ink: str = "bleu",
            dpi: float | None = None) -> Correction:
    """Corrige des fichiers scannés.

    ``pages`` donne le numéro de page du cahier (1 à 6) de chaque page scannée,
    dans l'ordre ; à défaut, il est déduit de la structure des pages.
    """
    scanned = [page for path in files for page in load_pages(path, dpi)]
    prepared = [prepare_page(page, ink) for page in scanned]
    numbers = pages or guess_page_numbers(prepared)
    if len(numbers) != len(scanned):
        raise ValueError(f"{len(scanned)} page(s) scannée(s) mais {len(numbers)} numéro(s) de page")
    return correct_pages([PageInput(scan, number, prep)
                          for scan, number, prep in zip(scanned, numbers, prepared)], ink)
