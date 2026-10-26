"""Enchaînement complet : scans -> zones -> tracés -> cotation."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Callable

import numpy as np

from .criteria import SUPPORTED_ITEMS, ItemResult, score_item
from .identify import better_page, resolve
from .layout import ITEMS_BY_PAGE, PreparedPage, prepare_page
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
    """Un item corrigé : proposition de l'outil (``result``) et, une fois l'item
    vérifié par l'ergothérapeute, les notes qu'il ou elle a changées."""

    item: int
    page: int
    source: str
    result: ItemResult
    drawing: Drawing
    zone_image: np.ndarray
    px_per_mm: float
    corrections: dict[str, int] = field(default_factory=dict)  # code -> note de l'ergo
    checked: bool = False  # vérifié par l'ergothérapeute

    def score(self, code: str) -> int | None:
        """Note retenue : celle de l'ergothérapeute si elle l'a changée."""
        automatic = self.result.score(code)
        return None if automatic is None else self.corrections.get(code, automatic)

    def total(self, *codes: str) -> int | None:
        scores = [self.score(code) for code in codes]
        return None if any(s is None for s in scores) else sum(scores)

    @property
    def to_review(self) -> bool:
        """Encore à vérifier : signalé par l'outil et pas encore vérifié."""
        return self.result.to_review and not self.checked

    def review(self, scores: dict[str, int]) -> None:
        """Enregistre la vérification de l'ergothérapeute : ``scores`` donne la note
        retenue de chaque critère, seules celles qui diffèrent de l'outil sont gardées."""
        unknown = set(scores) - set(self.result.criteria)
        if unknown:
            raise ValueError(f"item {self.item} : critère(s) {', '.join(sorted(unknown))} absent(s)")
        if any(score not in (0, 1) for score in scores.values()):
            raise ValueError(f"item {self.item} : une note vaut 0 ou 1")
        self.corrections = {code: score for code, score in scores.items()
                            if score != self.result.score(code)}
        self.checked = True


@dataclass
class Correction:
    items: list[ItemReport] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    pages: list[tuple[str, int]] = field(default_factory=list)  # (scan, page du cahier)
    child: str = ""  # pseudonyme ou initiales de l'enfant, saisi par l'ergothérapeute
    session_date: str = ""  # date de passation, telle que saisie


@dataclass
class PageInput:
    """Une page scannée à corriger et son numéro de page dans le cahier."""

    scan: ScannedPage
    number: int
    prepared: PreparedPage | None = None  # déjà redressée et orientée (même encre)
    guessed: bool = False  # numéro deviné sans certitude (voir identify.resolve)


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
        prepared = replace(prepared, px_per_mm=page.scan.dpi / MM_PAR_POUCE * prepared.scale)
        layout = prepared.layout(page.number)
        correction.pages.append((page.scan.source, page.number))
        # Doutes qui touchent toute la page : chacun de ses items est à vérifier.
        doubts = []
        if page.guessed:
            doubts.append(f"page du cahier devinée ({page_label(page.number)}), à confirmer : "
                          "une page manquante ou un scan seul rend le numéro incertain")
        other = better_page(prepared, page.number)
        if other is not None:
            doubts.append(f"les modèles imprimés ressemblent plutôt à la {page_label(other)} : "
                          "vérifier le numéro de page")
        separator_mm = layout.separator.length / layout.px_per_mm
        expected = SEPARATOR_MM.get(page.number, SEPARATOR_DEFAULT_MM)
        if abs(separator_mm - expected) > SEPARATOR_TOLERANCE * expected:
            doubts.append(f"échelle douteuse (trait de séparation de {separator_mm:.0f} mm), "
                          f"vérifier la résolution du scan ({page.scan.dpi:.0f} dpi)")
        correction.warnings.extend(f"{page.scan.source} : {doubt}" for doubt in doubts)
        for zone in layout.zones:
            if zone.item not in SUPPORTED_ITEMS:
                continue
            drawing = extract_drawing(layout.drawing_ink(zone.item), layout.px_per_mm)
            result = score_item(zone.item, drawing)
            result.notes.extend(doubts)
            x0, y0, x1, y1 = zone.drawing_box
            correction.items.append(ItemReport(
                zone.item, page.number, page.scan.source, result, drawing,
                layout.image[y0:y1, x0:x1].copy(), layout.px_per_mm))
    if progress:
        progress(len(inputs), len(inputs), "")
    correction.items.sort(key=lambda report: report.item)
    return correction


def correct(files: list[str | Path], pages: list[int] | None = None, ink: str = "bleu",
            dpi: float | None = None) -> Correction:
    """Corrige des fichiers scannés.

    ``pages`` donne le numéro de page du cahier (1 à 6) de chaque page scannée,
    dans l'ordre ; à défaut, il est déduit de la structure des pages et de leurs
    modèles imprimés, à condition qu'il soit sûr (voir ``identify.resolve``).
    """
    scanned = [page for path in files for page in load_pages(path, dpi)]
    prepared = [prepare_page(page, ink) for page in scanned]
    numbers, unsure = (pages, set()) if pages else resolve(prepared)
    if unsure:
        sources = ", ".join(scanned[index].source for index in sorted(unsure))
        raise ValueError(f"numéro de page du cahier incertain pour {sources} (page manquante ou "
                         "scan seul) : préciser le numéro de page de chaque scan avec --pages")
    if len(numbers) != len(scanned):
        raise ValueError(f"{len(scanned)} page(s) scannée(s) mais {len(numbers)} numéro(s) de page")
    return correct_pages([PageInput(scan, number, prep)
                          for scan, number, prep in zip(scanned, numbers, prepared)], ink)
