"""Chargement des pages scannées (PDF ou image) avec leur résolution."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageSequence, UnidentifiedImageError
from pypdf import PdfReader
from pypdf.errors import PyPdfError

MM_PAR_POUCE = 25.4
SCAN_SUFFIXES = (".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp")


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
    """Charge toutes les pages d'un fichier (PDF ou image, multipage ou non).

    Pour un PDF, la résolution est déduite de la taille de l'image scannée
    par rapport à la taille de la page. Pour une image, elle est lue dans les
    métadonnées, ou doit être fournie avec ``dpi``. Un fichier absent ou
    illisible lève ``ValueError`` avec un message lisible.
    """
    path = Path(path)
    if not path.is_file():
        raise ValueError(f"{path} : fichier introuvable")
    try:
        if path.suffix.lower() == ".pdf":
            return _load_pdf(path, dpi)
        return _load_images(path, dpi)
    except PyPdfError as error:
        raise ValueError(f"{path.name} : PDF illisible ({error})") from error
    except UnidentifiedImageError as error:
        raise ValueError(f"{path.name} : ni un PDF ni une image lisible") from error


def _load_pdf(path: Path, dpi: float | None) -> list[ScannedPage]:
    pages = []
    # Fichier fermé dès la lecture finie : le scan reste déplaçable sous Windows.
    with open(path, "rb") as stream:
        for index, page in enumerate(PdfReader(stream).pages, start=1):
            images = list(page.images)
            if not images:
                raise ValueError(f"{path.name} page {index} : aucune image scannée trouvée")
            pil = max((im.image for im in images), key=lambda im: im.width * im.height)
            page_width_in = float(page.mediabox.width) / 72
            page_dpi = dpi or pil.width / page_width_in
            bgr = cv2.cvtColor(np.asarray(pil.convert("RGB")), cv2.COLOR_RGB2BGR)
            pages.append(ScannedPage(bgr, page_dpi, f"{path.name} p{index}"))
    return pages


def _load_images(path: Path, dpi: float | None) -> list[ScannedPage]:
    """Toutes les pages d'une image : un TIFF peut en contenir plusieurs."""
    pages = []
    with Image.open(path) as pil:
        count = getattr(pil, "n_frames", 1)
        for index, frame in enumerate(ImageSequence.Iterator(pil), start=1):
            page_dpi = dpi
            if page_dpi is None and "dpi" in frame.info:
                page_dpi = float(frame.info["dpi"][0])
            if not page_dpi:
                raise ValueError(f"{path} : résolution inconnue, préciser --dpi")
            bgr = cv2.cvtColor(np.asarray(frame.convert("RGB")), cv2.COLOR_RGB2BGR)
            source = path.name if count == 1 else f"{path.name} p{index}"
            pages.append(ScannedPage(bgr, page_dpi, source))
    return pages


def natural_key(path: Path) -> list:
    """Clé de tri des noms de fichiers dans l'ordre naturel (« page 2 » avant « page 10 »)."""
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", path.name)]
