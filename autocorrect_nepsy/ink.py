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
MAX_PRINT_SATURATION = 60


def ink_mask(image_bgr: np.ndarray, ink: str = "bleu") -> np.ndarray:
    """Masque binaire (uint8 0/1) des pixels de l'encre de l'enfant."""
    if ink not in INK_HUES:
        raise ValueError(f"encre inconnue : {ink} (choix : {', '.join(INK_HUES)})")
    hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
    hue, sat = hsv[..., 0], hsv[..., 1]
    lo, hi = INK_HUES[ink]
    hue_ok = (hue >= lo) & (hue <= hi) if lo <= hi else (hue >= lo) | (hue <= hi)
    mask = (hue_ok & (sat >= MIN_INK_SATURATION)).astype(np.uint8)
    return cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))


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
