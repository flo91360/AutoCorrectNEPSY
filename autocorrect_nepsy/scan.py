"""Chargement des pages scannées (PDF ou image) avec leur résolution."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from pypdf import PdfReader

MM_PAR_POUCE = 25.4


@dataclass
class ScannedPage:
    """Une page scannée : image BGR et résolution du scan."""

    image: np.ndarray
    dpi: float
    source: str

    @property
    def px_per_mm(self) -> float:
        return self.dpi / MM_PAR_POUCE


def load_pages(path: str | Path, dpi: float | None = None) -> list[ScannedPage]:
    """Charge toutes les pages d'un fichier (PDF multi-pages ou image).

    Pour un PDF, la résolution est déduite de la taille de l'image scannée
    par rapport à la taille de la page. Pour une image, elle est lue dans les
    métadonnées, ou doit être fournie avec ``dpi``.
    """
    path = Path(path)
    if path.suffix.lower() == ".pdf":
        return _load_pdf(path, dpi)
    return [_load_image(path, dpi)]


def _load_pdf(path: Path, dpi: float | None) -> list[ScannedPage]:
    pages = []
    for index, page in enumerate(PdfReader(path).pages, start=1):
        images = list(page.images)
        if not images:
            raise ValueError(f"{path} page {index} : aucune image scannée trouvée")
        pil = max((im.image for im in images), key=lambda im: im.width * im.height)
        page_width_in = float(page.mediabox.width) / 72
        page_dpi = dpi or pil.width / page_width_in
        bgr = cv2.cvtColor(np.asarray(pil.convert("RGB")), cv2.COLOR_RGB2BGR)
        pages.append(ScannedPage(bgr, page_dpi, f"{path.name} p{index}"))
    return pages


def _load_image(path: Path, dpi: float | None) -> ScannedPage:
    with Image.open(path) as pil:
        if dpi is None and "dpi" in pil.info:
            dpi = float(pil.info["dpi"][0])
        bgr = cv2.cvtColor(np.asarray(pil.convert("RGB")), cv2.COLOR_RGB2BGR)
    if not dpi:
        raise ValueError(f"{path} : résolution inconnue, préciser --dpi")
    return ScannedPage(bgr, dpi, path.name)
