"""Séparation des encres : tracé de l'enfant, impression et crayon de l'ergo.

L'enfant dessine au stylo (bleu par défaut). L'impression du cahier et les
annotations de l'ergothérapeute au crayon à papier sont grises ou noires,
donc peu saturées : elles sont écartées du tracé de l'enfant.
"""

from __future__ import annotations

import cv2
import numpy as np

# Plages de teinte OpenCV (0-180) des encres de stylo reconnues.
INK_HUES = {
    "bleu": (95, 135),
    "rouge": (165, 10),
    "vert": (40, 90),
}
MIN_INK_SATURATION = 70
# Là où le stylo dépose plus d'encre, le trait devient presque noir et moins
# saturé : ces pixels sont gardés s'ils touchent un trait nettement coloré et
# s'ils sont au moins aussi foncés que la moitié du chemin entre le fond et
# l'encre (le liseré clair et flou au bord du trait n'est pas de l'encre).
MIN_DARK_INK_SATURATION = 40
DARK_INK_CONTRAST = 0.5
MAX_PRINT_SATURATION = 60
# Un trait de crayon (ou d'impression) qui croise le tracé de l'enfant le masque
# sur sa largeur : le tracé serait coupé en deux, puis compté comme deux
# éléments. Les pixels de crayon qui bouchent une coupure plus courte que
# BRIDGE_MM sont rendus au tracé.
BRIDGE_MM = 1.6
WORK_PX_PER_MM = 200 / 25.4  # résolution de travail (voir layout.WORK_DPI)


def ink_mask(image_bgr: np.ndarray, ink: str = "bleu",
             px_per_mm: float = WORK_PX_PER_MM) -> np.ndarray:
    """Masque binaire (uint8 0/1) des pixels de l'encre de l'enfant.

    Seuillage à deux niveaux : les pixels nettement colorés servent de point de
    départ, et les pixels de la même teinte mais plus foncés (encre épaisse)
    sont ajoutés quand ils les prolongent. Sans cela, un trait continu serait
    coupé là où l'encre est plus foncée, et compté comme interrompu. Le crayon
    de l'ergothérapeute, gris et sans teinte, reste exclu, sauf là où il coupe
    le tracé de l'enfant (voir ``BRIDGE_MM``).
    """
    if ink not in INK_HUES:
        raise ValueError(f"encre inconnue : {ink} (choix : {', '.join(INK_HUES)})")
    hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
    hue, sat = hsv[..., 0], hsv[..., 1]
    lo, hi = INK_HUES[ink]
    hue_ok = (hue >= lo) & (hue <= hi) if lo <= hi else (hue >= lo) | (hue <= hi)
    strong = (hue_ok & (sat >= MIN_INK_SATURATION)).astype(np.uint8)
    strong = cv2.morphologyEx(strong, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    if not strong.any():
        return strong
    value = hsv[..., 2].astype(np.float32)
    background = float(np.median(value))
    darkest = background - DARK_INK_CONTRAST * (background - float(np.median(value[strong > 0])))
    dark = hue_ok & (sat >= MIN_DARK_INK_SATURATION) & (value <= darkest)
    candidates = dark.astype(np.uint8) | strong
    count, labels = cv2.connectedComponents(candidates, connectivity=8)
    keep = np.zeros(count, bool)
    keep[np.unique(labels[strong > 0])] = True
    keep[0] = False
    child = keep[labels].astype(np.uint8)
    size = max(3, int(round(BRIDGE_MM * px_per_mm)) | 1)
    closed = cv2.morphologyEx(child, cv2.MORPH_CLOSE,
                              cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size)))
    return child | (closed & printed_mask(image_bgr))


def printed_mask(image_bgr: np.ndarray) -> np.ndarray:
    """Masque des traits sombres et peu saturés (impression, crayon)."""
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    sat = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)[..., 1]
    background = float(np.median(gray))
    dark = gray < background - max(30.0, 0.25 * background)
    return (dark & (sat < MAX_PRINT_SATURATION)).astype(np.uint8)


def faint_mask(image_bgr: np.ndarray) -> np.ndarray:
    """Masque large des traits peu saturés, y compris les traits gris clair
    du cahier (séparations entre zones), à peine plus sombres que le fond."""
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    sat = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)[..., 1]
    background = float(np.median(gray))
    dark = gray < background - max(6.0, 0.06 * background)
    return (dark & (sat < MAX_PRINT_SATURATION)).astype(np.uint8)
